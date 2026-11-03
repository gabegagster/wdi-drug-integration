"""Generate, merge, inspect, and select manually labeled medicine pairs."""

import argparse
from collections import defaultdict
import heapq
from pathlib import Path
import random
import re
import unicodedata
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


REPO_ROOT = Path(__file__).resolve().parents[2]
XML_DIR = REPO_ROOT / "data" / "4_translated_mapforce"
OUTPUT_DIR = REPO_ROOT / "data" / "5_golden_standard_pair"
DATASETS = ("dpd", "ema", "fda")
FIELDS = (
    "id", "source", "brandName", "activeSubstances", "activeSubstanceCount",
    "licenceHolder", "regulatoryStatus", "productClass", "atcCode", "generic",
    "biosimilar", "orphanMedicine", "dosageForm", "route", "strengths",
    "usApprovalDate", "euAuthorisationDate", "caStatusDate",
)
REVIEW_COLUMNS = ["pair_id"] + [
    f"{field}{side}" for side in (1, 2) for field in FIELDS
] + ["hard", "match"]


def normalize_text(value):
    """Normalize case, accents, punctuation, and whitespace in a string."""
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def pair_id(id1, id2):
    """Join record IDs in the fixed source order to make a readable pair ID."""
    if " <-> " in id1 or " <-> " in id2:
        raise ValueError("Record IDs must not contain the pair separator ' <-> '")
    return f"{id1} <-> {id2}"


def load_xml(path, source):
    """Load XML medicine records with unique IDs and comparison values."""
    records = []
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag.rsplit("}", 1)[-1] != "medicine":
            continue
        children = {child.tag.rsplit("}", 1)[-1]: child for child in element}
        record = {field: "" for field in FIELDS}
        ingredients = []
        for field, child in children.items():
            if field == "activeSubstances":
                ingredients = [(item.text or "").strip() for item in child]
                record[field] = "; ".join(ingredients)
            elif field == "strengths":
                strengths = []
                for item in child:
                    parts = {part.tag.rsplit("}", 1)[-1]: part.text or ""
                             for part in item}
                    strengths.append(f"{parts.get('value', '')} {parts.get('unit', '')}".strip())
                record[field] = "; ".join(strengths)
            elif field in record:
                record[field] = (child.text or "").strip()

        if record["source"].lower() != source:
            raise ValueError(f"Unexpected source in {path}: {record['source']}")
        record["brand_norm"] = normalize_text(record["brandName"])
        record["brand_tokens"] = frozenset(record["brand_norm"].split())
        record["ingredient_set"] = frozenset(
            normalized for item in ingredients
            if (normalized := normalize_text(item))
        )
        if not record["id"] or not record["brand_norm"] or not record["ingredient_set"]:
            raise ValueError(f"Missing ID, brand, or ingredients in {path}")
        records.append(record)
        element.clear()

    if not records:
        raise ValueError(f"No medicine records found in {path}")
    if len({row['id'] for row in records}) != len(records):
        raise ValueError(f"Duplicate record IDs in {path}")
    return records


def ranked_hard_pairs(left, right, limit, seed, excluded):
    """Return top unique candidates per strategy, excluding supplied index pairs."""
    rng = random.Random(seed)
    heaps = [[] for _ in range(4)]
    right_brand = defaultdict(list)
    right_composition_word = defaultdict(set)
    right_ingredient_word = defaultdict(set)

    # Index Right Records
    for j, record in enumerate(right):
        right_brand[record["brand_norm"]].append(j)
        composition = tuple(sorted(record["ingredient_set"]))
        for word in record["brand_tokens"]:
            right_composition_word[(composition, word)].add(j)
            for ingredient in record["ingredient_set"]:
                right_ingredient_word[(ingredient, word)].add(j)

    # Rank Strategies 1-3
    for i, record in enumerate(left):
        brand = record["brand_norm"]
        words = record["brand_tokens"]
        ingredients = record["ingredient_set"]
        composition = tuple(sorted(ingredients))
        same_composition = set()
        partial_composition = set()
        for word in words:
            same_composition.update(right_composition_word.get((composition, word), ()))
            for ingredient in ingredients:
                partial_composition.update(right_ingredient_word.get((ingredient, word), ()))

        candidate_groups = (
            right_brand.get(brand, ()),
            sorted(same_composition),
            sorted(partial_composition - same_composition),
        )
        for strategy, candidates in enumerate(candidate_groups):
            for j in candidates:
                if (i, j) in excluded:
                    continue
                other = right[j]
                same_brand = brand == other["brand_norm"]
                same_ingredients = ingredients == other["ingredient_set"]
                if strategy == 0 and same_ingredients:
                    continue
                if strategy in (1, 2) and same_brand:
                    continue
                ingredient_score = len(ingredients & other["ingredient_set"]) / len(
                    ingredients | other["ingredient_set"]
                )
                brand_score = len(words & other["brand_tokens"]) / len(
                    words | other["brand_tokens"]
                )
                score = ((ingredient_score, 0.0) if strategy == 0
                         else (brand_score, ingredient_score))
                entry = (*score, rng.random(), i, j)
                if len(heaps[strategy]) < limit:
                    heapq.heappush(heaps[strategy], entry)
                elif entry > heaps[strategy][0]:
                    heapq.heapreplace(heaps[strategy], entry)

    # Rank Brand Trigram TF-IDF
    brands = [row["brand_norm"] for row in left + right]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 3),
                                 lowercase=False, dtype=np.float32)
    try:
        matrix = vectorizer.fit_transform(brands)
    except ValueError as error:
        if "empty vocabulary" not in str(error):
            raise
        matrix = None
    if matrix is not None:
        left_matrix = matrix[:len(left)]
        right_matrix = matrix[len(left):]
        for start in range(0, len(left), 64):
            scores = (left_matrix[start:start + 64] @ right_matrix.T).tocsr()
            for offset in range(scores.shape[0]):
                i = start + offset
                begin, end = scores.indptr[offset:offset + 2]
                row_indices = scores.indices[begin:end]
                row_scores = scores.data[begin:end]
                # Sorting each sparse row keeps memory bounded by one batch.
                for position in row_scores.argsort()[::-1]:
                    j = int(row_indices[position])
                    score = float(row_scores[position])
                    if len(heaps[3]) == limit and score < heaps[3][0][0]:
                        break
                    if (i, j) in excluded or left[i]["brand_norm"] == right[j]["brand_norm"]:
                        continue
                    entry = (score, 0.0, rng.random(), i, j)
                    if len(heaps[3]) < limit:
                        heapq.heappush(heaps[3], entry)
                    elif entry > heaps[3][0]:
                        heapq.heapreplace(heaps[3], entry)

    return [[(entry[-2], entry[-1]) for entry in sorted(heap, reverse=True)]
            for heap in heaps]


def save_csv(frame, path):
    """Create a UTF-8 CSV, refusing to overwrite an existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        frame.to_csv(handle, index=False)
    print(f"Saved {len(frame):,} pairs: {path}")


def get_pairs(dataset1, dataset2, n, seed, output_dir, exclude):
    """Sample review pairs from two XML sources; write attributes and blank match labels."""
    if dataset1 == dataset2 or n < 1:
        raise ValueError("Choose two different datasets and a positive sample size")
    source1, source2 = sorted((dataset1, dataset2), key=DATASETS.index)
    output = Path(output_dir) / f"gs_{source1}_{source2}_raw.csv"
    if output.exists():
        raise FileExistsError(f"File already exists; use a new --output-dir: {output}")
    left = load_xml(XML_DIR / f"{source1}_medicines.xml", source1)
    right = load_xml(XML_DIR / f"{source2}_medicines.xml", source2)
    rng = random.Random(seed)

    # Exclude Previous Samples
    excluded = set()
    left_positions = {row["id"]: i for i, row in enumerate(left)}
    right_positions = {row["id"]: j for j, row in enumerate(right)}
    for filename in exclude:
        previous = read_reviews([filename])
        for row in previous.to_dict("records"):
            if row["source1"].lower() == source1 and row["source2"].lower() == source2:
                if row["id1"] not in left_positions or row["id2"] not in right_positions:
                    raise ValueError(f"Excluded sample contains IDs absent from current XML: {filename}")
                excluded.add((left_positions[row["id1"]], right_positions[row["id2"]]))
    if n > len(left) * len(right) - len(excluded):
        raise ValueError("Sample size exceeds the number of available unique pairs")

    # Select Hard Pool
    hard_count = n // 2
    easy_match_count = n // 5
    random_count = n - hard_count - easy_match_count
    selected = set(excluded)
    sample = []
    if hard_count:
        ranked = ranked_hard_pairs(left, right, hard_count, seed, excluded)
        quotas = [hard_count // 4 + (k < hard_count % 4) for k in range(4)]
        positions = [0] * 4
        counts = [0] * 4
        for strategy, quota in enumerate(quotas):
            while counts[strategy] < quota and positions[strategy] < len(ranked[strategy]):
                pair = ranked[strategy][positions[strategy]]
                positions[strategy] += 1
                if pair not in selected:
                    selected.add(pair)
                    sample.append((*pair, 1))
                    counts[strategy] += 1
        while len(sample) < hard_count:
            added = False
            for strategy in range(4):
                while positions[strategy] < len(ranked[strategy]):
                    pair = ranked[strategy][positions[strategy]]
                    positions[strategy] += 1
                    if pair not in selected:
                        selected.add(pair)
                        sample.append((*pair, 1))
                        counts[strategy] += 1
                        added = True
                        break
                if len(sample) == hard_count:
                    break
            if not added:
                raise ValueError(f"Hard-pool shortfall: need {hard_count}, found {len(sample)} unique pairs")
        print("Hard-pool selections: " + ", ".join(f"S{k + 1}={count}" for k, count in enumerate(counts)))

    # Sample Likely Ordinary Matches
    right_keys = defaultdict(list)
    for j, row in enumerate(right):
        right_keys[(row["brand_norm"], tuple(sorted(row["ingredient_set"])))].append(j)
    ordinary_candidates = []
    for i, row in enumerate(left):
        key = (row["brand_norm"], tuple(sorted(row["ingredient_set"])))
        ordinary_candidates.extend((i, j) for j in right_keys.get(key, ()) if (i, j) not in selected)
    if len(ordinary_candidates) < easy_match_count:
        raise ValueError(f"Likely-match pool shortfall: need {easy_match_count}, found {len(ordinary_candidates)}")
    for i, j in rng.sample(ordinary_candidates, easy_match_count):
        selected.add((i, j))
        sample.append((i, j, 0))

    # Sample Remaining Pairs
    available = len(left) * len(right) - len(selected)
    if random_count > available:
        raise ValueError("Random-pool shortfall after selecting hard and likely-match pairs")
    random_pairs = []
    if random_count and available * 2 < len(left) * len(right):
        # Dense exclusions are only practical to enumerate for small pair spaces.
        if len(left) * len(right) > 1_000_000:
            raise ValueError("Too many exclusions for efficient random sampling")
        remaining = [(i, j) for i in range(len(left)) for j in range(len(right))
                     if (i, j) not in selected]
        random_pairs = rng.sample(remaining, random_count)
    else:
        while len(random_pairs) < random_count:
            pair = (rng.randrange(len(left)), rng.randrange(len(right)))
            if pair not in selected:
                selected.add(pair)
                random_pairs.append(pair)
    sample.extend((i, j, 0) for i, j in random_pairs)

    # Build Review Rows
    rng.shuffle(sample)
    rows = []
    for i, j, hard in sample:
        record = {"pair_id": pair_id(left[i]["id"], right[j]["id"])}
        for side, medicine in ((1, left[i]), (2, right[j])):
            record.update({f"{field}{side}": medicine[field] for field in FIELDS})
        record.update(hard=hard, match="")
        rows.append(record)
    save_csv(pd.DataFrame(rows, columns=REVIEW_COLUMNS), output)
    print(f"Review groups: hard={hard_count}, likely ordinary matches={easy_match_count}, random={random_count}")


def read_reviews(inputs):
    """Read review CSVs as strings and validate pair identities and sampling groups."""
    frames = []
    for filename in inputs:
        frame = pd.read_csv(filename, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        required = {"pair_id", "id1", "id2", "source1", "source2", "hard", "match"}
        if missing := required - set(frame.columns):
            raise ValueError(f"Missing columns in {filename}: {sorted(missing)}")
        frame["match"] = frame["match"].str.strip()
        frame["hard"] = frame["hard"].str.strip()
        for index, row in zip(frame.index, frame.to_dict("records")):
            sources = (row["source1"].lower(), row["source2"].lower())
            if (any(source not in DATASETS for source in sources)
                    or sources[0] == sources[1]
                    or DATASETS.index(sources[0]) > DATASETS.index(sources[1])):
                raise ValueError(f"Invalid source order in {filename}: {sources}")
            expected = pair_id(row["id1"], row["id2"])
            if not row["id1"] or not row["id2"]:
                raise ValueError(f"Invalid pair identity in {filename}: {row['pair_id']}")
            # Rebuild from record IDs so earlier review files remain usable.
            frame.at[index, "pair_id"] = expected
            if row["hard"] not in ("0", "1"):
                raise ValueError(f"Invalid hard value in {filename}: {row['hard']!r}")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def merge_samples(inputs, output_dir):
    """Merge one source pair's fully labeled files; reject missing or conflicting labels."""
    rows = read_reviews(inputs)
    combinations = rows[["source1", "source2"]].apply(lambda col: col.str.lower()).drop_duplicates()
    if len(combinations) != 1:
        raise ValueError("Merge files for exactly one source combination at a time")
    # Check Labels Before Writing
    errors = []
    for key, group in rows.groupby("pair_id", sort=False):
        labels = set(group["match"])
        if "" in labels:
            errors.append(f"Missing match label: {key}")
        invalid = labels - {"", "0", "1"}
        if invalid:
            errors.append(f"Invalid match label {sorted(invalid)!r}: {key}; use 0 or 1")
        if {"0", "1"}.issubset(labels):
            errors.append(f"Different match labels (0 and 1): {key}")
    if errors:
        raise ValueError("Merging cannot be completed because of these label errors:\n"
                         + "\n".join(errors)
                         + "\nCorrect the listed pairs in the input files and merge again.")
    source1, source2 = combinations.iloc[0]
    output = Path(output_dir) / f"gs_{source1}_{source2}_unified.csv"
    if output.exists():
        raise FileExistsError("Unified file already exists; use a new --output-dir")

    # Merge Duplicate Labels
    merged = []
    for key, group in rows.groupby("pair_id", sort=False):
        record = group.iloc[0].to_dict()
        record["hard"] = str(group["hard"].astype(int).max())
        merged.append(record)
    save_csv(pd.DataFrame(merged, columns=rows.columns), output)
    print(f"Removed {len(rows) - len(merged):,} duplicate rows")


def check_labels(input_file):
    """Print match/group counts, percentages, missing labels, and duplicate conflicts."""
    rows = read_reviews([input_file])
    valid = rows[rows["match"].isin(["0", "1"])]
    duplicates = len(rows) - rows["pair_id"].nunique()
    conflict_ids = valid.groupby("pair_id")["match"].nunique().loc[lambda values: values > 1].index
    reviewed = valid[~valid["pair_id"].isin(conflict_ids)].drop_duplicates("pair_id").copy()
    max_hard = rows.groupby("pair_id")["hard"].max()
    reviewed["hard"] = reviewed["pair_id"].map(max_hard)
    print(f"Rows: {len(rows):,}; unique pairs: {rows['pair_id'].nunique():,}")
    print(f"Duplicate rows: {duplicates:,}; conflicting pair labels: {len(conflict_ids):,}")
    print(f"Unlabeled rows: {rows['match'].eq('').sum():,}; invalid labels: {(~rows['match'].isin(['', '0', '1'])).sum():,}")
    print("Percentages use unique pairs with a valid, non-conflicting 0/1 match label.")
    unique = rows.drop_duplicates("pair_id").copy()
    unique["hard"] = unique["pair_id"].map(max_hard)
    for sources, all_pairs in unique.groupby(["source1", "source2"], sort=True):
        group = reviewed[(reviewed["source1"] == sources[0]) & (reviewed["source2"] == sources[1])]
        print(f"\n{sources[0]} / {sources[1]}: {len(all_pairs):,} pairs, {len(group):,} reviewed")
        for hard, name in (("0", "Ordinary pool"), ("1", "Hard pool")):
            count = all_pairs["hard"].eq(hard).sum()
            print(f"{name:23} {count:7,} {100 * count / len(all_pairs):6.2f}% of all pairs")
        for hard, label, name in (("0", "1", "Ordinary match"), ("0", "0", "Ordinary non-match"),
                                  ("1", "1", "Hard-pool match"), ("1", "0", "Hard-pool non-match")):
            count = ((group["hard"] == hard) & (group["match"] == label)).sum()
            percentage = 100 * count / len(group) if len(group) else 0.0
            print(f"{name:23} {count:7,} {percentage:6.2f}% of reviewed pairs")


def select_pairs(input_file, size, seed, output_dir):
    """Select fixed 20/50/30 groups from resolved labels and export PyDI pairs."""
    if size < 1:
        raise ValueError("Selection size must be positive")
    rows = read_reviews([input_file])
    if rows["pair_id"].duplicated().any():
        raise ValueError("Merge duplicate pairs and resolve conflicts before selection")
    if not rows["match"].isin(["", "0", "1"]).all():
        raise ValueError("Invalid match labels; use blank, 0, or 1")
    combinations = rows[["source1", "source2"]].apply(lambda col: col.str.lower()).drop_duplicates()
    if len(combinations) != 1:
        raise ValueError("Select from exactly one source combination at a time")
    source1, source2 = combinations.iloc[0]
    output = Path(output_dir) / f"gs_{source1}_{source2}_selected.csv"
    pydi_output = Path(output_dir) / f"gs_{source1}_{source2}_pydi.csv"
    if output.exists() or pydi_output.exists():
        raise FileExistsError("Selected or PyDI file already exists; use a new --output-dir")

    # Check Group Sizes
    reviewed = rows[rows["match"].isin(["0", "1"])]
    counts = [size // 5, size // 2]
    counts.append(size - sum(counts))
    groups = [reviewed[(reviewed["hard"] == "0") & (reviewed["match"] == "1")],
              reviewed[reviewed["hard"] == "1"],
              reviewed[(reviewed["hard"] == "0") & (reviewed["match"] == "0")]]
    names = ["ordinary matches", "hard-pool pairs", "ordinary non-matches"]
    shortfalls = [f"{name}: need {count}, available {len(group)}, missing {count - len(group)}"
                  for name, count, group in zip(names, counts, groups) if len(group) < count]
    if shortfalls:
        raise ValueError("Selection shortfall:\n" + "\n".join(shortfalls))

    # Sample Resolved Labels
    selected = pd.concat([group.sample(n=count, random_state=seed)
                          for group, count in zip(groups, counts)], ignore_index=True)
    selected = selected.sample(frac=1, random_state=seed).reset_index(drop=True)
    pydi = selected[["id1", "id2", "match"]].rename(columns={"match": "label"})
    save_csv(selected, output)
    save_csv(pydi, pydi_output)
    print("Selected: " + ", ".join(f"{name}={count}" for name, count in zip(names, counts)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("get-pairs", help="Generate a CSV for manual match labeling")
    sample.add_argument("--dataset1", choices=DATASETS, required=True)
    sample.add_argument("--dataset2", choices=DATASETS, required=True)
    sample.add_argument("--n", type=int, default=500)
    sample.add_argument("--seed", type=int, default=42)
    sample.add_argument("--exclude", nargs="*", default=[], help="Previous review CSVs to skip")
    sample.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    merge = commands.add_parser("merge", help="Unify manually reviewed files for one source pair")
    merge.add_argument("--inputs", nargs="+", required=True)
    merge.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    stats = commands.add_parser("stats", help="Count reviewed labels and sampling groups")
    stats.add_argument("--input", required=True)
    select = commands.add_parser("select", help="Select fixed 20/50/30 proportions and export PyDI labels")
    select.add_argument("--input", required=True)
    select.add_argument("--size", type=int, required=True)
    select.add_argument("--seed", type=int, default=42)
    select.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    try:
        if args.command == "get-pairs":
            get_pairs(args.dataset1, args.dataset2, args.n, args.seed, args.output_dir, args.exclude)
        elif args.command == "merge":
            merge_samples(args.inputs, args.output_dir)
        elif args.command == "stats":
            check_labels(args.input)
        elif args.command == "select":
            select_pairs(args.input, args.size, args.seed, args.output_dir)
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()

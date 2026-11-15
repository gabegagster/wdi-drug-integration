"""Prepare supplied identity-resolution matches for PyDI.

With a match column, keep 1 rows and exclude 0 rows. Otherwise all supplied
pairs are positive matches. Default similarity 1.0 is an indicator, not a probability.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
import csv
import gzip
import importlib.util
import math
from pathlib import Path

import pandas as pd


def _frame(pairs):
    if isinstance(pairs, pd.DataFrame):
        return pairs.copy(), "provided DataFrame"
    path = Path(pairs)
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    if len(header) != len(set(header)):
        raise ValueError("Input CSV has duplicate column names.")
    return pd.read_csv(path, dtype="string", keep_default_na=False), str(path.resolve())


def _literal_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("IDs must be nonempty literal strings; missing IDs fail.")
    return value


def _score(value):
    if isinstance(value, bool):
        raise ValueError("Similarity must be a finite number between 0 and 1.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Similarity must be a finite number between 0 and 1.") from None
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("Similarity must be a finite number between 0 and 1.")
    return number


def prepare_correspondences(pairs, datasets):
    """Return id1/id2/similarity using current source-name-to-DataFrame datasets."""
    if not isinstance(datasets, Mapping) or not datasets:
        raise TypeError("datasets must map source names to current DataFrames.")
    sources = {}
    for source, dataset in datasets.items():
        if not isinstance(dataset, pd.DataFrame):
            raise TypeError("Every dataset must be a pandas DataFrame.")
        column = "_id" if "_id" in dataset else "id"
        if column not in dataset:
            raise ValueError(f"Dataset {source!r} has no id/_id column.")
        if "id" in dataset and "_id" in dataset and [_literal_id(v) for v in dataset["id"]] != [_literal_id(v) for v in dataset["_id"]]:
            raise ValueError(f"Dataset {source!r} has conflicting id and _id columns.")
        for value in dataset[column]:
            identifier = _literal_id(value)
            if identifier in sources:
                raise ValueError(f"Duplicate dataset ID: {identifier!r}")
            sources[identifier] = source
    frame, reference = _frame(pairs)
    if not frame.columns.is_unique or not {"id1", "id2"} <= set(frame.columns):
        raise ValueError("Pairs need unique column names including id1 and id2.")
    labelled = "match" in frame
    seen, positive, negative = {}, [], []
    duplicates = 0
    for row in frame.to_dict("records"):
        a, b = _literal_id(row["id1"]), _literal_id(row["id2"])
        if a not in sources or b not in sources:
            raise ValueError(f"Pair references an ID absent from current datasets: {a!r}, {b!r}")
        label = _score(int(row["match"]) if isinstance(row.get("match"), bool) else row["match"]) if labelled else 1.0
        if label not in (0.0, 1.0):
            raise ValueError("match labels must be explicit 0 or 1.")
        score = _score(row.get("similarity", row.get("score", 1.0)))
        if "similarity" in row and "score" in row and score != _score(row["score"]):
            raise ValueError("Conflicting score and similarity values.")
        key = tuple(sorted((a, b)))
        if key in seen:
            if seen[key] != (label, score):
                raise ValueError(f"Contradictory labels or conflicting duplicate scores: {key!r}")
            duplicates += 1
            continue
        seen[key] = (label, score)
        (positive if label else negative).append((a, b, score))
    parents = {identifier: identifier for identifier in sources}

    def find(identifier):
        while parents[identifier] != identifier:
            parents[identifier] = parents[parents[identifier]]
            identifier = parents[identifier]
        return identifier

    for a, b, _ in positive:
        left, right = find(a), find(b)
        if left == right:
            continue
        parents[right] = left
    if any(find(a) == find(b) for a, b, _ in negative):
        raise ValueError("A match=0 pair contradicts the positive connected group.")
    result = pd.DataFrame(positive, columns=["id1", "id2", "similarity"]).astype({"id1": "string", "id2": "string", "similarity": "float64"})
    result.attrs.update({
        "input_reference": reference,
        "input_rows": len(frame), "positive_pairs": len(result),
        "excluded_negative_pairs": len(negative), "duplicate_rows_removed": duplicates,
        "groups": len({find(a) for a, _, _ in positive}),
        "grouped_records": len({identifier for a, b, _ in positive for identifier in (a, b)}),
        "source_pair_counts": dict(Counter("_".join(sorted((str(sources[a]), str(sources[b])))) for a, b, _ in positive)),
        "score_semantics": "Default 1.0 indicates a positive pair, not a probability.",
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional CSV; an identical existing result is reused.")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--xml-dir", type=Path)
    args = parser.parse_args()
    try:
        spec = importlib.util.spec_from_file_location("sibling_loader", Path(__file__).resolve().with_name("loader.py"))
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        print("1/2 Loading XMLs with loader.py", flush=True)
        datasets = loader.load_datasets(args.project_root, xml_dir=args.xml_dir)
        loader.print_summary(datasets)
        print("\n2/2 Preparing pairs with correspondence_prep.py", flush=True)
        result = prepare_correspondences(args.input, datasets)
        output_note = None
        if args.output is not None:
            output = args.output.resolve()
            project_root = Path(args.project_root or loader.PROJECT_ROOT).resolve()
            protected = [project_root / "data", project_root / "src/mapforce"]
            if args.xml_dir is not None:
                protected.append(args.xml_dir.resolve())
            if output == args.input.resolve() or any(output.is_relative_to(folder.resolve()) for folder in protected):
                raise ValueError("Choose an output outside source data folders and different from the input.")
            content = result.to_csv(index=False).encode("utf-8")
            if output.exists():
                if output.samefile(args.input) or output.read_bytes() != content:
                    raise ValueError(f"Existing output differs or is the input; file left unchanged: {output}")
                output_note = f"Output unchanged: {output}"
            else:
                with output.open("xb") as stream:
                    stream.write(content)
                output_note = f"Output: {output}"
        print("Correspondence preparation complete")
        print(f"Input: {args.input.resolve()}")
        print(f"Pairs: {len(result):,}; groups: {result.attrs['groups']:,}; grouped records: {result.attrs['grouped_records']:,}")
        print("Source pairs: " + ", ".join(f"{name}={count:,}" for name, count in sorted(result.attrs["source_pair_counts"].items())))
        if output_note:
            print(output_note)
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"Correspondence preparation failed: {error}\n")


if __name__ == "__main__":
    main()

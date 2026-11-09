"""Combine labeled medicine pairs and create a shared stratified train/test split."""

import argparse
import math
from pathlib import Path

from sklearn.model_selection import train_test_split

from gold_standard_pair_gen import OUTPUT_DIR, REVIEW_COLUMNS, read_reviews, save_csv


COMPLETE_DIR = OUTPUT_DIR / "golden_standard_pair_complete"


def combine_split(inputs, output_dir=COMPLETE_DIR, train_ratio=0.85, test_ratio=0.15, seed=42):
    """Combine fully labeled review CSVs, save whole/train_val/test sets, and return them."""
    if not inputs:
        raise ValueError("Provide at least one labeled pair CSV")
    if not 0 < train_ratio < 1 or not 0 < test_ratio < 1:
        raise ValueError("Train and test ratios must be between 0 and 1")
    if not math.isclose(train_ratio + test_ratio, 1.0):
        raise ValueError("Train and test ratios must sum to 1")

    # Show Settings
    print("Input files:")
    for filename in inputs:
        print(f"  {filename}")
    print(f"Requested split: train_val={train_ratio:.2%}, test={test_ratio:.2%}")
    print(f"Seed: {seed}")
    print("Stratification: source_pair, hard, match")
    print(f"Output directory: {output_dir}")

    # Load Pairs
    whole = read_reviews(inputs)
    if whole.empty:
        raise ValueError("Input files contain no pairs")
    if not whole["match"].isin(["0", "1"]).all():
        raise ValueError("Every pair needs a match label of 0 or 1")
    if whole["pair_id"].duplicated().any():
        raise ValueError("Duplicate pairs found; provide non-overlapping unified datasets")
    whole["source_pair"] = whole["source1"].str.lower() + "_" + whole["source2"].str.lower()
    columns = [column for column in REVIEW_COLUMNS if column in whole.columns]
    columns += sorted(column for column in whole.columns if column not in columns)
    whole = whole[columns].fillna("")
    whole = whole.sort_values("pair_id").reset_index(drop=True)

    # Split Pairs
    strata = whole["source_pair"] + "|" + whole["hard"] + "|" + whole["match"]
    if strata.value_counts().min() < 2:
        raise ValueError("Each source_pair/hard/match group needs at least two pairs")
    train_val, test = train_test_split(
        whole, test_size=test_ratio, random_state=seed, stratify=strata,
    )
    train_val = train_val.reset_index(drop=True)
    test = test.reset_index(drop=True)

    # Show Split
    print(f"\nWhole set: {len(whole):,} pairs")
    print(f"Train/validation: {len(train_val):,} pairs ({len(train_val) / len(whole):.2%})")
    print(f"Test: {len(test):,} pairs ({len(test) / len(whole):.2%})")
    counts = whole.groupby("source_pair").size().to_frame("whole")
    counts["train_val"] = train_val.groupby("source_pair").size()
    counts["test"] = test.groupby("source_pair").size()
    print("\nPairs by source:")
    print(counts.fillna(0).astype(int).to_string())
    print("\nTest pairs by source, pool, and label:")
    print(test.groupby(["source_pair", "hard", "match"]).size().to_string())

    # Save Sets
    output_dir = Path(output_dir)
    outputs = [output_dir / f"gs_pair_{name}.csv" for name in ("whole", "train_val", "test")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("Output files already exist; use a new --output-dir")
    print("\nOutput files:")
    for frame, path in zip((whole, train_val, test), outputs):
        save_csv(frame, path)
    return whole, train_val, test


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True, help="Fully labeled review CSVs")
    parser.add_argument("--train-ratio", type=float, default=0.85)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=COMPLETE_DIR)
    args = parser.parse_args()
    try:
        combine_split(args.inputs, args.output_dir, args.train_ratio, args.test_ratio, args.seed)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()

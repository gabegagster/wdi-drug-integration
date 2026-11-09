"""Verify Phase II dependencies with a tiny, offline PyDI matching example."""

import sys
from importlib.metadata import version
from tempfile import TemporaryDirectory

import pandas as pd
import PyDI.io
import PyDI.fusion
from PyDI.entitymatching import RuleBasedMatcher, StandardBlocker, StringComparator


def main():
    left = pd.DataFrame([
        {"id": "us_1", "brandName": "ExampleDrug", "activeSubstances": "ibuprofen"},
    ])
    right = pd.DataFrame([
        {"id": "eu_1", "brandName": "ExampleDrug", "activeSubstances": "ibuprofen"},
        {"id": "eu_2", "brandName": "ExampleDrug", "activeSubstances": "amoxicillin"},
        {"id": "eu_3", "brandName": "OtherBrand", "activeSubstances": "ibuprofen"},
    ])
    left.attrs["dataset_name"] = "synthetic_us"
    right.attrs["dataset_name"] = "synthetic_eu"
    with TemporaryDirectory(prefix="pydi-check-") as output_dir:
        candidates = StandardBlocker(
            left, right, on=["brandName"], id_column="id", output_dir=output_dir
        ).materialize()
        if set(zip(candidates.id1, candidates.id2)) != {("us_1", "eu_1"), ("us_1", "eu_2")}:
            raise RuntimeError("Unexpected blocking results")
        matches = RuleBasedMatcher().match(
            df_left=left, df_right=right, candidates=candidates, id_column="id",
            comparators=[StringComparator("brandName", similarity_function="jaro_winkler"),
                         StringComparator("activeSubstances", similarity_function="jaro_winkler")],
            weights=[0.5, 0.5], threshold=0.99,
        )
        if set(zip(matches.id1, matches.id2)) != {("us_1", "eu_1")}:
            raise RuntimeError("Unexpected matching results")
    print(f"Python {sys.version.split()[0]}: {sys.executable}")
    for package in ("uma-pydi", "pandas", "numpy", "scikit-learn", "jupyter", "lxml", "jsonschema"):
        print(f"{package}=={version(package)}")
    print("PASS: PyDI IO/fusion imports, blocking and string-based matching")


if __name__ == "__main__":
    main()

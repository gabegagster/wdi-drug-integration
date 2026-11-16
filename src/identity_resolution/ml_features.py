"""Pairwise similarity features for the ML matchers.

The six features of ``notebooks/ml_classifier_experiment/ml_classifier_experiment.ipynb`` (SVM + Logistic
Regression), moved into a module so that every ML classifier (SVM, LR, Random
Forest, Gradient Boosting) uses identical inputs and the same code can later
score the blocking candidates.

The ``hard`` column is never used as a feature: it only records the sampling
pool of the gold standard and is not available for blocking candidates.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

COMPANY_SUFFIXES = {
    "LTD", "LIMITED", "INC", "INCORPORATED", "CORP", "CORPORATION",
    "CO", "COMPANY", "LLC", "LLP", "PLC", "GMBH", "AG",
    "BV", "NV", "SA", "SAS", "SRL", "SPA",
}

COMMON_SALTS = {
    "HYDROCHLORIDE", "HCL", "DIHYDROCHLORIDE", "MONOHYDROCHLORIDE",
    "SODIUM", "POTASSIUM", "CALCIUM", "MAGNESIUM", "ZINC",
    "SULFATE", "SULPHATE", "PHOSPHATE", "ACETATE", "CITRATE",
    "TARTRATE", "MALEATE", "FUMARATE", "SUCCINATE", "LACTATE",
    "NITRATE", "BROMIDE", "IODIDE", "CHLORIDE", "GLUCONATE",
    "MONOHYDRATE", "DIHYDRATE", "TRIHYDRATE", "ANHYDROUS", "HYDRATE",
    "BESYLATE", "MESYLATE", "TOSYLATE", "EMBONATE", "PAMOATE",
    "VALERATE", "PROPIONATE", "BUTYRATE", "DECANOATE", "ENANTHATE",
}

FEATURE_NAMES = [
    "brand_sim", "substance_sim", "substance_token_jaccard",
    "holder_sim", "holder_missing", "substance_count_diff",
]


def normalise(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"[^\w\s]", " ", text.upper()).strip()


def seq_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def overlap_coeff(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    smaller = min(len(set_a), len(set_b))
    if smaller == 0:
        return 0.0
    return len(set_a & set_b) / smaller


def _feature_row(row: pd.Series) -> list[float]:
    b1, b2 = normalise(row["brandName1"]), normalise(row["brandName2"])
    s1, s2 = normalise(row["activeSubstances1"]), normalise(row["activeSubstances2"])
    h1, h2 = normalise(row["licenceHolder1"]), normalise(row["licenceHolder2"])

    tok1 = set(s1.split()) - COMMON_SALTS
    tok2 = set(s2.split()) - COMMON_SALTS
    htok1 = set(h1.split()) - COMPANY_SUFFIXES
    htok2 = set(h2.split()) - COMPANY_SUFFIXES
    holder_missing = 1 if (not h1 or not h2) else 0

    cnt1 = row.get("activeSubstanceCount1", len(tok1))
    cnt2 = row.get("activeSubstanceCount2", len(tok2))
    count_diff = abs(float(cnt1) - float(cnt2)) if pd.notna(cnt1) and pd.notna(cnt2) else 0.0

    return [
        seq_sim(b1, b2),
        seq_sim(s1, s2),
        jaccard(tok1, tok2),
        overlap_coeff(htok1, htok2) if not holder_missing else 0.0,
        float(holder_missing),
        count_diff,
    ]


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the 6 similarity features for each pair (same values as the SVM/LR notebook)."""
    rows = [_feature_row(r) for _, r in df.iterrows()]
    return pd.DataFrame(rows, columns=FEATURE_NAMES, index=df.index)

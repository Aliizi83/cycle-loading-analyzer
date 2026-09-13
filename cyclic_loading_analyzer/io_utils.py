"""Input file reading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_raw_data(path: str | Path) -> pd.DataFrame:
    """Read Time/Stress/Strain columns from a CSV or XLSX file.

    Column position determines role, not header text, UNLESS the first
    three headers unambiguously spell out "time", "stress" and "strain"
    (case-insensitive, any order) — in that case they're used to reorder
    the columns, since some export tools put strain before stress. For
    any other header text, column 1 is Time, column 2 Stress, column 3
    Strain, regardless of what they're labeled. Extra columns beyond the
    first three are ignored.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported input file type: {suffix!r} (expected .csv or .xlsx)")

    if df.shape[1] < 3:
        raise ValueError(
            f"Input file must have at least 3 columns (Time, Stress, Strain); found {df.shape[1]}"
        )

    first_three = df.columns[:3]
    normalized = [str(c).strip().lower() for c in first_three]
    if set(normalized) == {"time", "stress", "strain"}:
        by_name = dict(zip(normalized, first_three))
        df = df[[by_name["time"], by_name["stress"], by_name["strain"]]].copy()
    else:
        df = df.iloc[:, :3].copy()
    df.columns = ["Time", "Stress", "Strain"]
    df = df.apply(pd.to_numeric, errors="coerce")
    if df.isna().any().any():
        n_bad = int(df.isna().any(axis=1).sum())
        raise ValueError(
            f"Input file contains {n_bad} row(s) with non-numeric values in Time/Stress/Strain"
        )

    return df.reset_index(drop=True)

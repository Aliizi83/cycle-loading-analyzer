"""Input file reading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_raw_data(path: str | Path) -> pd.DataFrame:
    """Read Time/Stress/Strain columns from a CSV or XLSX file.

    Column position determines role, not header text: column 1 is
    always treated as Time, column 2 as Stress, column 3 as Strain,
    regardless of their header labels. Extra columns beyond the first
    three are ignored.
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

    df = df.iloc[:, :3].copy()
    df.columns = ["Time", "Stress", "Strain"]
    df = df.apply(pd.to_numeric, errors="coerce")
    if df.isna().any().any():
        n_bad = int(df.isna().any(axis=1).sum())
        raise ValueError(
            f"Input file contains {n_bad} row(s) with non-numeric values in Time/Stress/Strain"
        )

    return df.reset_index(drop=True)

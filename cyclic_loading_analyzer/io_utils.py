"""Input file reading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read_table(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, nrows=nrows)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, nrows=nrows)
    raise ValueError(f"Unsupported input file type: {suffix!r} (expected .csv or .xlsx)")


def peek_column_count(path: str | Path) -> int:
    """Return the number of columns in a CSV/XLSX file without loading its rows."""
    return _read_table(path, nrows=0).shape[1]


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
    df = _read_table(path)

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


def read_single_signal_data(path: str | Path) -> tuple[pd.DataFrame, str]:
    """Read Time + one signal column (e.g. Extension) from a CSV or XLSX file.

    Column 1 is Time, column 2 is the signal, by position, regardless of
    header text. The signal's original header text is kept and returned
    alongside the data so callers can label sheets/charts with it. Extra
    columns beyond the first two are ignored.
    """
    df = _read_table(path)

    if df.shape[1] < 2:
        raise ValueError(f"Input file must have at least 2 columns (Time, signal); found {df.shape[1]}")

    signal_name = str(df.columns[1]).strip() or "Signal"
    df = df.iloc[:, :2].copy()
    df.columns = ["Time", signal_name]
    df = df.apply(pd.to_numeric, errors="coerce")
    if df.isna().any().any():
        n_bad = int(df.isna().any(axis=1).sum())
        raise ValueError(
            f"Input file contains {n_bad} row(s) with non-numeric values in Time/{signal_name}"
        )

    return df.reset_index(drop=True), signal_name

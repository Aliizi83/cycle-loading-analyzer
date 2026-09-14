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


def _drop_cycle_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop any column named "Cycle" (case-insensitive).

    `add_cycle_columns.py` inserts a per-row cycle-number label next to
    each signal (see `cycle_labeling.py`); that's derived output, not a
    signal to read, so it's excluded before positional Time/Stress/Strain
    (or Time/<signal>) detection runs. A no-op for files without one.

    Matches by *prefix*, not exact equality: a file with two "Cycle"
    columns (one per signal group) has the second renamed "Cycle.1" by
    pandas on read (duplicate headers), same as "Time" -> "Time.1" — an
    exact match would only catch the first and misread the second as a
    real data column.
    """
    keep = [c for c in df.columns if not str(c).strip().lower().startswith("cycle")]
    return df[keep]


def _extract_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Turn a DataFrame's first 3 columns into a clean Time/Stress/Strain frame.

    Column position determines role, not header text, UNLESS the first
    three headers unambiguously spell out "time", "stress" and "strain"
    (case-insensitive, any order) — in that case they're used to reorder
    the columns, since some export tools put strain before stress. For
    any other header text, column 1 is Time, column 2 Stress, column 3
    Strain, regardless of what they're labeled.
    """
    first_three = df.columns[:3]
    normalized = [str(c).strip().lower() for c in first_three]
    if set(normalized) == {"time", "stress", "strain"}:
        by_name = dict(zip(normalized, first_three))
        out = df[[by_name["time"], by_name["stress"], by_name["strain"]]].copy()
    else:
        out = df.iloc[:, :3].copy()
    out.columns = ["Time", "Stress", "Strain"]
    out = out.apply(pd.to_numeric, errors="coerce")
    if out.isna().any().any():
        n_bad = int(out.isna().any(axis=1).sum())
        raise ValueError(
            f"Input file contains {n_bad} row(s) with non-numeric values in Time/Stress/Strain"
        )
    return out.reset_index(drop=True)


def read_raw_data(path: str | Path) -> pd.DataFrame:
    """Read Time/Stress/Strain columns (1-3) from a CSV or XLSX file.

    Extra columns beyond the first three are ignored. See
    `read_combined_data` to also read a Time/<signal> pair from columns 4-5.
    """
    df = _drop_cycle_columns(_read_table(path))
    if df.shape[1] < 3:
        raise ValueError(
            f"Input file must have at least 3 columns (Time, Stress, Strain); found {df.shape[1]}"
        )
    return _extract_signal_columns(df)


def read_combined_data(
    path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame | None, str | None]:
    """Read a raw_data file that may carry a second, independently-sampled signal.

    Columns 1-3 are always Time/Stress/Strain (see `_extract_signal_columns`
    for the header-matching rules). Columns 4-5, if present, are a second
    Time + <signal> pair (e.g. Time + Extension from an LVDT) — sampled by
    a different device, so it commonly has a different row count than the
    first three columns. When the two parts were combined into one file by
    laying them out side by side, the shorter one is padded with blank
    cells out to the longer one's row count; those padding rows are
    dropped here based on the second pair's own blanks, not the first
    three columns' length.

    Returns (main_df with columns ["Time","Stress","Strain"],
    second_df with columns ["Time", <signal name>] or None if columns 4-5
    aren't present or are entirely blank, signal_name or None).
    """
    df = _drop_cycle_columns(_read_table(path))
    if df.shape[1] < 3:
        raise ValueError(
            f"Input file must have at least 3 columns (Time, Stress, Strain); found {df.shape[1]}"
        )
    main_df = _extract_signal_columns(df)

    second_df = None
    signal_name = None
    if df.shape[1] >= 5:
        signal_name = str(df.columns[4]).strip() or "Signal"
        second = df.iloc[:, 3:5].copy()
        second.columns = ["Time", signal_name]
        second = second.apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
        if len(second) > 0:
            second_df = second
        else:
            signal_name = None

    return main_df, second_df, signal_name


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

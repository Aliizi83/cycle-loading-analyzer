"""Interactive CLI: build "corrected" raw_data files by substituting Strain
from a reference Stress/Strain curve, matched by Stress.

Run:

    python build_corrected_raw_data.py

You pick ONE file from raw_data/ and one or more files from correct_data/
(each correct_data file has its own Stress/Strain reference curve — e.g. a
monotonic pull test on the same material). For every (raw_data file,
correct_data file) pair, this writes raw_data_correct/<N>-<M>.xlsx, where
N is the raw_data file's leading number and M is the correct_data file's
stem — e.g. raw_data "28 - raw.xlsx" + correct_data "1.xlsx" ->
raw_data_correct/28-1.xlsx.

The new file has the exact same Time/Stress (and Extension, if present)
columns as the source raw_data file — untouched. Only Strain changes: for
each row, its Stress value is looked up in the correct_data file's own
Stress/Strain curve, and the matching (or interpolated) Strain from THAT
curve replaces the row's original Strain.

Matching a raw Stress value against correct_data's curve:

1. correct_data's own (Stress, Strain) points are grouped by Stress,
   rounded to N decimal places (you're asked for N) -- many rows in a
   real reference curve share the exact same recorded Stress while
   Strain still varies (sensor resolution, or a real yield/damage
   plateau), so grouping the curve into one Strain value per rounded
   Stress (the group's average) is needed before it can be treated as a
   function to look up.
2. Every raw Stress value is then read off this grouped curve by linear
   interpolation -- this naturally reduces to an exact lookup when the
   raw Stress coincides with a curve point, and to interpolation
   between the two nearest curve points otherwise.
3. A raw Stress value outside correct_data's own observed range is
   clamped to the nearest end of that range before the lookup (per raw
   file 28 / correct_data 1.xlsx: file 28's Stress dips slightly below
   correct_data's minimum during unload; those rows are clamped to that
   minimum rather than extrapolated).
4. If a raw_data file's Stress range doesn't overlap correct_data's
   range AT ALL, clamping would be meaningless (every row would map to
   the same single point) -- that pair is refused with an error instead
   of silently producing a flat, meaningless Strain column.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from cyclic_loading_analyzer.excel_writer import CHART_MAX_POINTS, add_dual_axis_stress_strain_chart
from cyclic_loading_analyzer.io_utils import read_combined_data

PROJECT_DIR = Path(__file__).parent
RAW_DIR = PROJECT_DIR / "raw_data"
CORRECT_DIR = PROJECT_DIR / "correct_data"
OUTPUT_DIR = PROJECT_DIR / "raw_data_correct"

DEFAULT_DECIMALS = 12


def _file_number(path: Path) -> str:
    m = re.match(r"(\d+)", path.name)
    return m.group(1) if m else path.stem


def _list_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in (".xlsx", ".xls", ".csv"))


def _prompt_single_choice(files: list[Path], label: str) -> Path:
    print(f"\n=== {label} ===")
    for i, p in enumerate(files, start=1):
        print(f"  {i}) {p.name}")
    while True:
        raw = input(f"Select ONE {label} file (number): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return files[int(raw) - 1]
        print(f"  Enter a number from 1 to {len(files)}.")


def _prompt_multi_choice(files: list[Path], label: str) -> list[Path]:
    print(f"\n=== {label} ===")
    for i, p in enumerate(files, start=1):
        print(f"  {i}) {p.name}")
    while True:
        raw = input(f"Select {label} file(s), comma-separated numbers (e.g. 1,3): ").strip()
        parts = [x.strip() for x in raw.split(",") if x.strip()]
        if parts and all(x.isdigit() and 1 <= int(x) <= len(files) for x in parts):
            seen = []
            for x in parts:
                p = files[int(x) - 1]
                if p not in seen:
                    seen.append(p)
            return seen
        print(f"  Enter one or more numbers from 1 to {len(files)}, comma-separated.")


def _prompt_decimals() -> int:
    raw = input(f"Decimal places for grouping correct_data's Stress values [default {DEFAULT_DECIMALS}]: ").strip()
    if not raw:
        return DEFAULT_DECIMALS
    try:
        return int(raw)
    except ValueError:
        print(f"  Not a whole number, using default ({DEFAULT_DECIMALS}).")
        return DEFAULT_DECIMALS


def read_correct_data(path: Path) -> pd.DataFrame:
    """Read a correct_data file's Stress/Strain columns, whatever case
    their headers use ("Stress"/"Strain" in some files, "stress"/"strain"
    in others) -- normalized to "Stress"/"Strain" for everything downstream.
    """
    df = pd.read_excel(path)
    stress_col = next((c for c in df.columns if str(c).strip().lower() == "stress"), None)
    strain_col = next((c for c in df.columns if str(c).strip().lower() == "strain"), None)
    if stress_col is None or strain_col is None:
        raise ValueError(f"{path.name}: expected Stress/Strain columns, found {list(df.columns)}")
    return df[[stress_col, strain_col]].rename(columns={stress_col: "Stress", strain_col: "Strain"})


def build_lookup_curve(correct_df: pd.DataFrame, decimals: int) -> tuple[np.ndarray, np.ndarray]:
    """Reduce correct_data's (Stress, Strain) points to one averaged Strain
    per Stress value, rounded to `decimals` places, sorted ascending by
    Stress -- a clean function ready for `np.interp`.
    """
    df = correct_df.dropna(subset=["Stress", "Strain"])
    stress = np.round(df["Stress"].to_numpy(dtype=float), decimals)
    strain = df["Strain"].to_numpy(dtype=float)

    order = np.argsort(stress, kind="stable")
    stress_sorted = stress[order]
    strain_sorted = strain[order]

    unique_stress, inverse = np.unique(stress_sorted, return_inverse=True)
    sums = np.zeros(len(unique_stress))
    counts = np.zeros(len(unique_stress))
    np.add.at(sums, inverse, strain_sorted)
    np.add.at(counts, inverse, 1)
    avg_strain = sums / counts
    return unique_stress, avg_strain


def find_negative_reference(correct_files: list[Path]) -> Path | None:
    """The correct_data file, if any, whose Stress values are entirely
    <= 0 -- a dedicated reference curve for the negative/compression side
    (e.g. "n-13.xlsx"), used instead of the main ruler file for any raw
    row whose Stress is negative, since a ruler file covering only the
    positive/tension side has nothing valid to interpolate there.

    Errors if more than one file qualifies (ambiguous which to use).
    """
    candidates = [p for p in correct_files if read_correct_data(p)["Stress"].max() <= 0]
    if len(candidates) > 1:
        raise SystemExit(
            "ERROR: more than one correct_data file has an entirely non-positive Stress range "
            f"({', '.join(p.name for p in candidates)}) -- ambiguous which is the negative-side reference."
        )
    return candidates[0] if candidates else None


def corrected_strain(
    raw_stress: np.ndarray,
    curve_stress: np.ndarray,
    curve_strain: np.ndarray,
    neg_curve_stress: np.ndarray | None = None,
    neg_curve_strain: np.ndarray | None = None,
) -> np.ndarray:
    """Look up Strain for every raw Stress value on correct_data's curve.

    Values outside [curve_stress.min(), curve_stress.max()] are clamped to
    that boundary before interpolation (see module docstring point 3) --
    `np.interp` does this automatically for out-of-range x.

    If `neg_curve_stress`/`neg_curve_strain` are given, any row with a
    NEGATIVE raw Stress is looked up on that curve instead of the main
    one -- see `find_negative_reference`.
    """
    result = np.interp(raw_stress, curve_stress, curve_strain)
    if neg_curve_stress is not None:
        neg_mask = raw_stress < 0
        if neg_mask.any():
            result[neg_mask] = np.interp(raw_stress[neg_mask], neg_curve_stress, neg_curve_strain)
    return result


def process_pair(
    raw_path: Path,
    correct_path: Path,
    decimals: int,
    negative_reference_path: Path | None = None,
) -> Path:
    main_df, ext_df, ext_name = read_combined_data(raw_path)
    correct_df = read_correct_data(correct_path)

    curve_stress, curve_strain = build_lookup_curve(correct_df, decimals)
    print(
        f"  correct_data curve: {len(curve_stress)} distinct Stress points "
        f"(range {curve_stress.min():.4f} to {curve_stress.max():.4f}) after grouping to {decimals} decimals"
    )

    neg_curve_stress = neg_curve_strain = None
    if negative_reference_path is not None:
        neg_df = read_correct_data(negative_reference_path)
        neg_curve_stress, neg_curve_strain = build_lookup_curve(neg_df, decimals)
        print(
            f"  negative-side reference ({negative_reference_path.name}): {len(neg_curve_stress)} distinct "
            f"Stress points (range {neg_curve_stress.min():.4f} to {neg_curve_stress.max():.4f})"
        )

    raw_stress = main_df["Stress"].to_numpy()
    raw_min, raw_max = float(raw_stress.min()), float(raw_stress.max())
    # The positive-side check only applies to non-negative raw Stress when
    # a negative reference is handling the rest.
    positive_raw = raw_stress[raw_stress >= 0] if negative_reference_path is not None else raw_stress
    curve_min, curve_max = float(curve_stress.min()), float(curve_stress.max())

    if len(positive_raw) and (positive_raw.max() < curve_min or positive_raw.min() > curve_max):
        raise SystemExit(
            f"ERROR: {raw_path.name} Stress range [{raw_min:.4f}, {raw_max:.4f}] does not overlap "
            f"{correct_path.name} Stress range [{curve_min:.4f}, {curve_max:.4f}] at all -- "
            "refusing to produce a meaningless flat-clamped Strain column."
        )

    n_below = int((positive_raw < curve_min).sum())
    n_above = int((positive_raw > curve_max).sum())
    if n_below:
        print(f"  {n_below} row(s) below curve minimum ({curve_min:.4f}) -- clamped to it.")
    if n_above:
        print(f"  {n_above} row(s) above curve maximum ({curve_max:.4f}) -- clamped to it.")

    new_strain = corrected_strain(raw_stress, curve_stress, curve_strain, neg_curve_stress, neg_curve_strain)

    time = main_df["Time"].to_numpy()
    stress = main_df["Stress"].to_numpy()
    series_list = [
        pd.Series(time, name="Time"),
        pd.Series(stress, name="Stress"),
        pd.Series(new_strain, name="Strain"),
    ]

    if ext_df is not None:
        ext_time = ext_df["Time"].to_numpy()
        ext_values = ext_df[ext_name].to_numpy()
        n = max(len(main_df), len(ext_df))
        series_list = [s.reindex(range(n)) for s in series_list]
        series_list.append(pd.Series(ext_time, name="Time").reindex(range(n)))
        series_list.append(pd.Series(ext_values, name=ext_name).reindex(range(n)))

    out = pd.concat(series_list, axis=1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{_file_number(raw_path)}-{correct_path.stem}.xlsx"
    out.to_excel(output_path, index=False)
    add_overlay_chart(output_path, len(out))
    return output_path


def add_overlay_chart(output_path: Path, n_rows: int) -> None:
    """Add the big Stress+Strain-vs-Time dual-axis chart (see
    excel_writer.add_dual_axis_stress_strain_chart) directly to a
    raw_data_correct file, right after writing it -- reopens the file,
    since pandas' own .to_excel can't add charts.

    Columns 1-3 in the file `to_excel` just wrote are always
    Time/Stress/Strain (see process_pair). Downsamples to at most
    CHART_MAX_POINTS rows for the chart series when there are more than
    that, same as the main pipeline's charts -- referencing all rows
    directly for a multi-hundred-thousand-row file would make the chart
    (and Excel itself) sluggish.
    """
    wb = load_workbook(output_path)
    data_ws = wb.active
    last_row = n_rows + 1

    if n_rows > CHART_MAX_POINTS:
        step = (n_rows // CHART_MAX_POINTS) + 1
        helper_ws = wb.create_sheet("_chart_data")
        helper_ws.sheet_state = "hidden"
        for col in range(1, 4):
            helper_ws.cell(row=1, column=col, value=data_ws.cell(row=1, column=col).value)
        out_row = 2
        for r in range(2, n_rows + 2, step):
            for col in range(1, 4):
                helper_ws.cell(row=out_row, column=col, value=data_ws.cell(row=r, column=col).value)
            out_row += 1
        source_ws = helper_ws
        source_last_row = out_row - 1
    else:
        source_ws = data_ws
        source_last_row = last_row

    chart = add_dual_axis_stress_strain_chart(source_ws, 1, 2, 3, source_last_row)
    charts_ws = wb.create_sheet("Charts")
    charts_ws.add_chart(chart, "A1")
    wb.save(output_path)


def main() -> int:
    raw_files = _list_files(RAW_DIR)
    correct_files = _list_files(CORRECT_DIR)
    if not raw_files:
        raise SystemExit(f"No files found in {RAW_DIR}")
    if not correct_files:
        raise SystemExit(f"No files found in {CORRECT_DIR}")

    negative_reference_path = find_negative_reference(correct_files)
    selectable = [p for p in correct_files if p != negative_reference_path]
    if negative_reference_path:
        print(
            f"(using {negative_reference_path.name} automatically for any negative Stress -- "
            "not offered as a selectable ruler itself)"
        )

    raw_path = _prompt_single_choice(raw_files, "raw_data")
    correct_paths = _prompt_multi_choice(selectable, "correct_data")
    decimals = _prompt_decimals()

    for correct_path in correct_paths:
        print(f"\nProcessing {raw_path.name} x {correct_path.name}...")
        output_path = process_pair(raw_path, correct_path, decimals, negative_reference_path)
        print(f"  -> {output_path.relative_to(PROJECT_DIR)}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

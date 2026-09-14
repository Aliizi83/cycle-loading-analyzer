"""One-off migration: add per-row "Cycle" columns to every raw_data file.

Inserts a "Cycle" column right before Stress/Strain (labeling every row
by which Stress zero-to-zero cycle it falls in — see
`cycle_labeling.zero_crossing_boundaries`), and, for files with a 4th/5th
column, another "Cycle" column right before that signal (e.g. Extension —
labeled by its own peak-to-peak cycles, since it doesn't cross zero, via
`cycle_labeling.peak_to_peak_boundaries`).

For files 19-22, every two consecutive cycles are relabeled "1_1","1_2",
"2_1","2_2",... (see `cross_reference.paired_cycle_label`) instead of
plain integers, matching the same convention already used in those
files' cross-reference sheets.

Overwrites each raw_data file in place. Run once; re-running is safe
(idempotent) since it always rebuilds from the original 3/5 signal
columns, ignoring any Cycle columns already present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from cyclic_loading_analyzer.cli import cycles_for_signal
from cyclic_loading_analyzer.cross_reference import paired_cycle_label
from cyclic_loading_analyzer.cycle_labeling import (
    cycle_labels,
    peak_to_peak_boundaries,
    zero_crossing_boundaries,
)
from cyclic_loading_analyzer.io_utils import read_combined_data

SHOW_LAST_CYCLE = True
PAIRED_CYCLE_FILE_NUMBERS = {19, 20, 21, 22}

RAW_DIR = Path(__file__).parent / "raw_data"


def _file_number(path: Path) -> int | None:
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else None


def main() -> int:
    paths = sorted(RAW_DIR.glob("*.xlsx"))
    for path in paths:
        number = _file_number(path)
        cycle_label_fn = paired_cycle_label if number in PAIRED_CYCLE_FILE_NUMBERS else None

        main_df, ext_df, ext_name = read_combined_data(path)
        time = main_df["Time"].to_numpy()
        stress = main_df["Stress"].to_numpy()
        strain = main_df["Strain"].to_numpy()

        stress_cycles, _th, _m = cycles_for_signal(time, stress, None, SHOW_LAST_CYCLE)
        main_boundaries = zero_crossing_boundaries(time, stress, stress_cycles)
        main_labels = cycle_labels(time, main_boundaries, cycle_label_fn)

        # Column names come from main_df/ext_df's own (already header-
        # corrected) labels, never from the file's raw positional header
        # text — some files have "time, strain, stress" in that literal
        # order, and read_combined_data already untangled that; reusing
        # the raw positional text here would silently swap the labels
        # right back.
        # pd.concat (not a dict literal) is required to keep two columns
        # both literally named "Cycle" — a dict would silently drop one.
        series_list = [
            pd.Series(time, name="Time"),
            pd.Series(main_labels, name="Cycle"),
            pd.Series(stress, name="Stress"),
            pd.Series(strain, name="Strain"),
        ]

        if ext_df is not None:
            ext_time = ext_df["Time"].to_numpy()
            ext_values = ext_df[ext_name].to_numpy()
            ext_cycles, _th2, _m2 = cycles_for_signal(ext_time, ext_values, None, SHOW_LAST_CYCLE)
            ext_boundaries = peak_to_peak_boundaries(ext_cycles)
            ext_labels = cycle_labels(ext_time, ext_boundaries, cycle_label_fn)

            n = max(len(main_df), len(ext_df))
            series_list = [s.reindex(range(n)) for s in series_list]
            series_list.append(pd.Series(ext_time, name="Time").reindex(range(n)))
            series_list.append(pd.Series(ext_labels, name="Cycle").reindex(range(n)))
            series_list.append(pd.Series(ext_values, name=ext_name).reindex(range(n)))

        out = pd.concat(series_list, axis=1)
        out.to_excel(path, index=False)
        print(f"{path.name}: {len(main_df)} main rows" + (f", {len(ext_df)} {ext_name} rows" if ext_df is not None else ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())

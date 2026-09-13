"""Simplified fixed-configuration batch runner.

No CLI flags, no interactive prompts: drop one or more raw data files into
raw_data/, then run:

    python run.py

Each file is processed independently. For raw_data/<name>.xlsx, the
output is written to results/<name>_result.xlsx — one workbook with every
signal the file carries: Stress + Strain (columns 1-3, always), plus a
third signal like Extension (columns 4-5, independently sampled) when
present.

Thresholds are auto-computed per file (see the constants below) as a
fraction of each signal's own peak-to-peak range, so files with different
amplitudes don't need separate manual tuning. Set a constant to a fixed
number instead of None to override auto-computation for every file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from cyclic_loading_analyzer.cli import process
from cyclic_loading_analyzer.cross_reference import paired_cycle_label

STRESS_THRESHOLD = None  # None = auto-compute; or set a fixed number, e.g. 10.0
STRAIN_THRESHOLD = None  # None = auto-compute; or set a fixed number, e.g. 0.0005
EXTENSION_THRESHOLD = None  # threshold for a 4th/5th-column signal (e.g. Extension), if present
SHOW_LAST_CYCLE = True

# For these specific files, every two consecutive detected cycles in the
# cross-reference sheets (Stress Max, Stress Min, ..., Combined) represent
# one physical loading cycle — relabel them "1_1","1_2","2_1","2_2",...
# instead of the plain 1,2,3,4,... Every other file keeps plain numbering.
PAIRED_CYCLE_FILE_NUMBERS = {19, 20, 21, 22}

PROJECT_DIR = Path(__file__).parent
INPUT_DIR = PROJECT_DIR / "raw_data"
OUTPUT_DIR = PROJECT_DIR / "results"
INPUT_SUFFIXES = (".xlsx", ".xls", ".csv")


def find_input_files() -> list[Path]:
    return sorted(p for p in INPUT_DIR.iterdir() if p.suffix.lower() in INPUT_SUFFIXES)


def _file_number(path: Path) -> int | None:
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else None


def main() -> int:
    input_files = find_input_files()
    if not input_files:
        raise SystemExit(
            f"No input files found in {INPUT_DIR}\n"
            "Put your raw data file(s) (.xlsx or .csv) in that folder and "
            "run this script again."
        )

    for input_path in input_files:
        output_path = OUTPUT_DIR / f"{input_path.stem}_result.xlsx"
        cycle_label_fn = paired_cycle_label if _file_number(input_path) in PAIRED_CYCLE_FILE_NUMBERS else None
        result = process(
            input_path,
            output_path,
            STRESS_THRESHOLD,
            STRAIN_THRESHOLD,
            EXTENSION_THRESHOLD,
            SHOW_LAST_CYCLE,
            cycle_label_fn,
        )

        parts = [f"{o.n_cycles} {o.name.lower()} cycles [threshold {o.threshold:g}]" for o in result.outcomes]
        print(
            f"{input_path.name} -> {output_path.relative_to(PROJECT_DIR)} "
            f"({', '.join(parts)}, {result.raw_rows} raw rows)"
        )

        merged_parts = [f"{o.reversals_merged} {o.name.lower()}" for o in result.outcomes if o.reversals_merged]
        if merged_parts:
            print(f"    removed brief secondary reversals: {', '.join(merged_parts)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Simplified fixed-configuration batch runner.

No CLI flags, no interactive prompts: drop one or more raw data files
(Time, Stress, Strain columns, in that order) into raw_data/, then run:

    python run.py

Each file is processed independently. For raw_data/<name>.xlsx, the
output is written to results/<name>_result.xlsx.

Edit the constants below to change the thresholds for a different dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cyclic_loading_analyzer.cli import process

STRESS_THRESHOLD = 10.0
STRAIN_THRESHOLD = 0.0005
SHOW_LAST_CYCLE = True

PROJECT_DIR = Path(__file__).parent
INPUT_DIR = PROJECT_DIR / "raw_data"
OUTPUT_DIR = PROJECT_DIR / "results"
INPUT_SUFFIXES = (".xlsx", ".xls", ".csv")


def find_input_files() -> list[Path]:
    return sorted(p for p in INPUT_DIR.iterdir() if p.suffix.lower() in INPUT_SUFFIXES)


def main() -> int:
    input_files = find_input_files()
    if not input_files:
        raise SystemExit(
            f"No input files found in {INPUT_DIR}\n"
            "Put your raw data file(s) (.xlsx or .csv, columns in Time, "
            "Stress, Strain order) in that folder and run this script again."
        )

    for input_path in input_files:
        output_path = OUTPUT_DIR / f"{input_path.stem}_result.xlsx"
        stress_cycles, strain_cycles, raw_rows = process(
            input_path, output_path, STRESS_THRESHOLD, STRAIN_THRESHOLD, SHOW_LAST_CYCLE
        )
        print(
            f"{input_path.name} -> {output_path.relative_to(PROJECT_DIR)} "
            f"({stress_cycles} stress cycles, {strain_cycles} strain cycles, {raw_rows} raw rows)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

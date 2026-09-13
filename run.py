"""Simplified fixed-configuration runner.

No CLI flags, no interactive prompts: put your raw data file (Time, Stress,
Strain columns, in that order) in the excel/ folder next to this script,
then just run:

    python run.py

The output workbook is written next to the input file, with "_results"
appended to its name.

Edit the constants below to change the thresholds or the input folder for a
different dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cyclic_loading_analyzer.cli import process

STRESS_THRESHOLD = 10.0
STRAIN_THRESHOLD = 0.0005
SHOW_LAST_CYCLE = True

EXCEL_DIR = Path(__file__).parent / "excel"
INPUT_SUFFIXES = (".xlsx", ".xls", ".csv")


def find_input_file() -> Path:
    candidates = [
        p
        for p in sorted(EXCEL_DIR.iterdir())
        if p.suffix.lower() in INPUT_SUFFIXES and not p.stem.endswith("_results")
    ]
    if not candidates:
        raise SystemExit(
            f"No input file found in {EXCEL_DIR}\n"
            "Put your raw data file (.xlsx or .csv, columns in Time, Stress, "
            "Strain order) in that folder and run this script again."
        )
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise SystemExit(
            f"Found more than one input file in {EXCEL_DIR}: {names}\n"
            "Keep only one raw data file in that folder."
        )
    return candidates[0]


def main() -> int:
    input_path = find_input_file()
    output_path = input_path.with_name(input_path.stem + "_results.xlsx")

    stress_cycles, strain_cycles, raw_rows = process(
        input_path, output_path, STRESS_THRESHOLD, STRAIN_THRESHOLD, SHOW_LAST_CYCLE
    )

    print(
        f"Wrote {output_path} "
        f"({stress_cycles} stress cycles, {strain_cycles} strain cycles, {raw_rows} raw rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

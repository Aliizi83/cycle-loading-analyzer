"""One-command batch pipeline: raw data -> results -> Si.

No CLI flags, no interactive prompts: drop one or more raw data files into
raw_data/, then run:

    python run.py

This runs the full pipeline in one go, every time:

1. `add_cycle_columns`: rewrites every raw_data file in place, adding the
   per-row "Cycle" columns next to Stress/Strain and next to Extension
   (if present). Safe to redo on every run — it always rebuilds from the
   original 3/5 signal columns.
2. For each raw_data/<name>.xlsx, writes results/<name>_result.xlsx — one
   workbook with every signal the file carries: Stress + Strain (columns
   1-3, always), plus a third signal like Extension (columns 4-5,
   independently sampled) when present.
3. `compute_si`: adds the Si sheet + chart to every results workbook that
   has an Extension signal.

Thresholds are auto-computed per file (see the constants below) as an
adaptive fraction of each signal's own peak-to-peak range — see
`detector.suggest_threshold` for how it handles ratcheting tests, where
early cycles are much smaller than later ones. Set a constant to a fixed
number instead of None to override auto-computation for every file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import add_cycle_columns
import compute_si
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

    print("=== Step 1/3: adding Cycle columns to raw_data files ===", flush=True)
    add_cycle_columns.main()

    print("\n=== Step 2/3: generating results/ workbooks ===", flush=True)
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
            f"({', '.join(parts)}, {result.raw_rows} raw rows)",
            flush=True,
        )

        merged_parts = [f"{o.reversals_merged} {o.name.lower()}" for o in result.outcomes if o.reversals_merged]
        if merged_parts:
            print(f"    removed brief secondary reversals: {', '.join(merged_parts)}", flush=True)

    print("\n=== Step 3/3: computing Si ===", flush=True)
    compute_si.main()

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

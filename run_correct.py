"""Run the exact same per-file pipeline as run.py, but on raw_data_correct/
files, writing to results_correct/ -- plus the large Stress/Strain overlay
chart (see excel_writer.write_workbook's stress_strain_overlay), which is
specific to this "corrected" pipeline, not the main one.

    python run_correct.py

Each file in raw_data_correct/ (see build_corrected_raw_data.py /
build_corrected_raw_data_batch.py) is named <N>-<correct_data stem>.xlsx,
where N is the original raw_data file's number -- e.g. "28-1.xlsx" came
from raw_data file 28. That leading number N is all this uses to decide
the file's rules (paired cycle labeling, which Si formula), so a
corrected file gets processed with EXACTLY the same rules its original
raw_data file would have.

Files are processed in parallel (see WORKER_COUNT), same reasoning as
run.py -- there can be many of these (e.g. 15 raw_data files x several
correct_data rulers).
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from cyclic_loading_analyzer.cli import process
from cyclic_loading_analyzer.cross_reference import paired_cycle_label
from run import (
    EXTENSION_THRESHOLD,
    LVDT_MAX_SI_FILE_NUMBERS,
    PAIRED_CYCLE_FILE_NUMBERS,
    SHOW_LAST_CYCLE,
    STRAIN_THRESHOLD,
    STRESS_THRESHOLD,
    ZERO_CROSSING_SI_FILE_NUMBERS,
    _file_number,
    find_input_files,
)

PROJECT_DIR = Path(__file__).parent
INPUT_DIR = PROJECT_DIR / "raw_data_correct"
OUTPUT_DIR = PROJECT_DIR / "results_correct"
WORKER_COUNT = 4


@dataclass
class FileTask:
    input_path: Path
    output_path: Path
    cycle_label_fn_name: str | None
    si_kind: str | None


def _run_one(task: FileTask) -> dict:
    start = time.time()
    cycle_label_fn = paired_cycle_label if task.cycle_label_fn_name == "paired" else None
    result = process(
        task.input_path,
        task.output_path,
        STRESS_THRESHOLD,
        STRAIN_THRESHOLD,
        EXTENSION_THRESHOLD,
        SHOW_LAST_CYCLE,
        cycle_label_fn,
        task.si_kind,
        task.input_path,  # also add Cycle columns to raw_data_correct's own file, same as raw_data/
        True,  # stress_strain_overlay
    )
    parts = [f"{o.n_cycles} {o.name.lower()} cycles [threshold {o.threshold:g}]" for o in result.outcomes]
    return {
        "name": task.input_path.name,
        "output_path": task.output_path,
        "line": f"({', '.join(parts)}, {result.raw_rows} raw rows)",
        "elapsed": time.time() - start,
    }


def main() -> int:
    input_files = find_input_files(INPUT_DIR)
    if not input_files:
        raise SystemExit(
            f"No files found in {INPUT_DIR}\n"
            "Run build_corrected_raw_data.py or build_corrected_raw_data_batch.py first."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks = []
    for input_path in input_files:
        number = _file_number(input_path)
        si_kind = (
            "zero_crossing"
            if number in ZERO_CROSSING_SI_FILE_NUMBERS
            else "lvdt_max"
            if number in LVDT_MAX_SI_FILE_NUMBERS
            else None
        )
        tasks.append(
            FileTask(
                input_path=input_path,
                output_path=OUTPUT_DIR / f"{input_path.stem}_result.xlsx",
                cycle_label_fn_name="paired" if number in PAIRED_CYCLE_FILE_NUMBERS else None,
                si_kind=si_kind,
            )
        )

    print(f"Processing {len(tasks)} file(s) with {WORKER_COUNT} worker(s)...", flush=True)

    n_done = 0
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for future in as_completed(futures):
            task = futures[future]
            n_done += 1
            try:
                outcome = future.result()
            except Exception as exc:  # noqa: BLE001 - report and keep going
                print(f"[{n_done}/{len(tasks)}] {task.input_path.name}: FAILED - {exc}", flush=True)
                continue
            print(
                f"[{n_done}/{len(tasks)}] {outcome['name']} -> {outcome['output_path'].relative_to(PROJECT_DIR)} "
                f"{outcome['line']} ({outcome['elapsed']:.1f}s)",
                flush=True,
            )

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Non-interactive batch version of build_corrected_raw_data.py: every
raw_data file x every correct_data "ruler" file, in parallel.

    python build_corrected_raw_data_batch.py

Unlike the interactive script (pick one raw_data file, pick one or more
correct_data files), this always does the full cartesian product: all
raw_data/*.xlsx x all correct_data/*.xlsx EXCEPT the negative-side
reference file (see build_corrected_raw_data.find_negative_reference,
e.g. "n-13.xlsx") -- that one is never a selectable ruler on its own, it's
used automatically for any row whose raw Stress is negative, same as in
the interactive script.

Output goes to raw_data_correct/<N>-<ruler stem>.xlsx, same naming as the
interactive script. With 15 raw_data files x 7 ruler files that's 105
files, each involving reading a multi-hundred-thousand-row raw_data file
-- run with a small process pool (see WORKER_COUNT) since each pair is
fully independent.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from build_corrected_raw_data import (
    CORRECT_DIR,
    PROJECT_DIR,
    RAW_DIR,
    DEFAULT_DECIMALS,
    _list_files,
    find_negative_reference,
    process_pair,
)

WORKER_COUNT = 8


@dataclass
class PairTask:
    raw_path: Path
    correct_path: Path
    decimals: int
    negative_reference_path: Path | None


def _run_one(task: PairTask) -> dict:
    start = time.time()
    output_path = process_pair(task.raw_path, task.correct_path, task.decimals, task.negative_reference_path)
    return {
        "raw": task.raw_path.name,
        "correct": task.correct_path.name,
        "output": output_path,
        "elapsed": time.time() - start,
    }


def main() -> int:
    raw_files = _list_files(RAW_DIR)
    correct_files = _list_files(CORRECT_DIR)
    if not raw_files:
        raise SystemExit(f"No files found in {RAW_DIR}")
    if not correct_files:
        raise SystemExit(f"No files found in {CORRECT_DIR}")

    negative_reference_path = find_negative_reference(correct_files)
    ruler_files = [p for p in correct_files if p != negative_reference_path]

    print(f"{len(raw_files)} raw_data file(s) x {len(ruler_files)} ruler file(s) = {len(raw_files) * len(ruler_files)} pair(s)")
    if negative_reference_path:
        print(f"(negative Stress rows use {negative_reference_path.name} automatically)")
    print(f"Decimal places for grouping correct_data's Stress values: {DEFAULT_DECIMALS}\n", flush=True)

    tasks = [
        PairTask(raw_path, correct_path, DEFAULT_DECIMALS, negative_reference_path)
        for raw_path in raw_files
        for correct_path in ruler_files
    ]

    n_done = 0
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for future in as_completed(futures):
            task = futures[future]
            n_done += 1
            try:
                outcome = future.result()
            except Exception as exc:  # noqa: BLE001 - report and keep going
                print(f"[{n_done}/{len(tasks)}] {task.raw_path.name} x {task.correct_path.name}: FAILED - {exc}", flush=True)
                continue
            print(
                f"[{n_done}/{len(tasks)}] {outcome['raw']} x {outcome['correct']} "
                f"-> {outcome['output'].relative_to(PROJECT_DIR)} ({outcome['elapsed']:.1f}s)",
                flush=True,
            )

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

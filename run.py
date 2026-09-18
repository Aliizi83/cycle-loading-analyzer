"""One-command batch pipeline: raw data -> results -> Si.

No CLI flags, no interactive prompts: drop one or more raw data files into
raw_data/, then run:

    python run.py

For each raw_data/<name>.xlsx this reads the file ONCE, detects cycles
ONCE per signal, then in one pass:

1. Writes results/<name>_result.xlsx — one workbook with every signal the
   file carries (Stress + Strain, plus Extension if present), the
   cross-reference sheets, and the Si sheet + chart (if the file has an
   Extension signal) — all in the same save, not three separate scripts
   re-reading and re-writing the same files.
2. Rewrites the raw_data file in place with the per-row "Cycle" columns
   (see `cycle_labeling`) — but ONLY if that file's content has actually
   changed since the last successful run (tracked by content hash in
   raw_data/.pipeline_manifest.json), since re-detecting and rewriting a
   multi-hundred-thousand-row file is the most expensive part of the
   whole pipeline and produces byte-identical output when nothing about
   the source data or detection logic changed.

Files are processed in parallel (see WORKER_COUNT) since each is fully
independent.

Thresholds are auto-computed per file (see the constants below) as an
adaptive fraction of each signal's own peak-to-peak range — see
`detector.suggest_threshold` for how it handles ratcheting tests, where
early cycles are much smaller than later ones. Set a constant to a fixed
number instead of None to override auto-computation for every file.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
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

# Which Si formula each file uses (see cyclic_loading_analyzer/si.py) —
# None for files with no Extension signal, where Si can't be computed.
ZERO_CROSSING_SI_FILE_NUMBERS = {16, 17, 18}
LVDT_MAX_SI_FILE_NUMBERS = {19, 20, 21, 22, 23, 24, 25, 26, 27, 28}

# Bounded well below the machine's core count / free RAM: each worker
# can hold a multi-hundred-thousand-row workbook in memory at once (seen
# over 1GB for the largest files), so too many at once risks swapping
# rather than actually going faster.
WORKER_COUNT = 4

PROJECT_DIR = Path(__file__).parent
INPUT_DIR = PROJECT_DIR / "raw_data"
OUTPUT_DIR = PROJECT_DIR / "results"
INPUT_SUFFIXES = (".xlsx", ".xls", ".csv")


def find_input_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.suffix.lower() in INPUT_SUFFIXES)


def _file_number(path: Path) -> int | None:
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else None


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(manifest_path: Path) -> dict[str, str]:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {}


def _save_manifest(manifest_path: Path, manifest: dict[str, str]) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


@dataclass
class FileTask:
    input_path: Path
    output_path: Path
    cycle_label_fn_name: str | None  # "paired" or None — picklable across process boundary
    si_kind: str | None
    needs_migration: bool


def _cycle_label_fn_from_name(name: str | None):
    return paired_cycle_label if name == "paired" else None


def _run_one(task: FileTask) -> dict:
    start = time.time()
    cycle_label_fn = _cycle_label_fn_from_name(task.cycle_label_fn_name)
    write_cycle_columns_to = task.input_path if task.needs_migration else None

    result = process(
        task.input_path,
        task.output_path,
        STRESS_THRESHOLD,
        STRAIN_THRESHOLD,
        EXTENSION_THRESHOLD,
        SHOW_LAST_CYCLE,
        cycle_label_fn,
        task.si_kind,
        write_cycle_columns_to,
    )

    new_hash = _file_hash(task.input_path) if task.needs_migration else None

    parts = [f"{o.n_cycles} {o.name.lower()} cycles [threshold {o.threshold:g}]" for o in result.outcomes]
    merged_parts = [f"{o.reversals_merged} {o.name.lower()}" for o in result.outcomes if o.reversals_merged]
    lines = [
        f"{task.input_path.name} -> {task.output_path.relative_to(PROJECT_DIR)} "
        f"({', '.join(parts)}, {result.raw_rows} raw rows)"
        + (" [raw_data unchanged, skipped Cycle-column rewrite]" if not task.needs_migration else ""),
    ]
    if merged_parts:
        lines.append(f"    removed brief secondary reversals: {', '.join(merged_parts)}")

    return {
        "name": task.input_path.name,
        "hash": new_hash,
        "lines": lines,
        "elapsed": time.time() - start,
    }


def main(input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR, manifest_path: Path | None = None) -> int:
    """Run the full pipeline for every file in `input_dir`, writing to
    `output_dir`. Defaults to raw_data/ -> results/; pass different
    directories (see run_correct.py) to run the exact same pipeline over
    a different set of raw_data-shaped files.
    """
    if manifest_path is None:
        manifest_path = input_dir / ".pipeline_manifest.json"

    input_files = find_input_files(input_dir)
    if not input_files:
        raise SystemExit(
            f"No input files found in {input_dir}\n"
            "Put your raw data file(s) (.xlsx or .csv) in that folder and "
            "run this script again."
        )

    manifest = _load_manifest(manifest_path)

    tasks = []
    for input_path in input_files:
        number = _file_number(input_path)
        current_hash = _file_hash(input_path)
        needs_migration = manifest.get(input_path.name) != current_hash
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
                output_path=output_dir / f"{input_path.stem}_result.xlsx",
                cycle_label_fn_name="paired" if number in PAIRED_CYCLE_FILE_NUMBERS else None,
                si_kind=si_kind,
                needs_migration=needs_migration,
            )
        )

    skipped = sum(1 for t in tasks if not t.needs_migration)
    print(
        f"Processing {len(tasks)} file(s) with {WORKER_COUNT} worker(s) "
        f"({skipped} unchanged since last run, skipping their Cycle-column rewrite)...",
        flush=True,
    )

    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:  # noqa: BLE001 - report and keep going
                print(f"{task.input_path.name}: FAILED - {exc}", flush=True)
                continue

            for line in outcome["lines"]:
                print(line, flush=True)
            print(f"    ({outcome['elapsed']:.1f}s)", flush=True)

            if outcome["hash"] is not None:
                manifest[outcome["name"]] = outcome["hash"]
                _save_manifest(manifest_path, manifest)  # incremental, so a crash mid-batch doesn't lose earlier progress

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

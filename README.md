# cyclic-loading-analyzer

Reads cyclic loading test data (Time, Stress, Strain), detects the Max/Min
point of every loading cycle for both the Stress and Strain signals using a
hysteresis (threshold-reversal) filter, and writes a formatted Excel
workbook with the per-cycle results and native charts.

## Requirements

- Python 3.9+
- pandas, numpy, openpyxl (installed via `requirements.txt` below)

## Installation

```bash
cd cyclic-loading-analyzer
python3 -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

You only need to do this once. Every time you come back to use the tool in
a new terminal, just re-activate the virtual environment:

```bash
cd cyclic-loading-analyzer
source .venv/bin/activate
```

## How to run it (manual walkthrough)

There are two ways to run the tool: **interactive** (it asks you questions)
or **flag-based** (you pass everything on the command line, good for
scripts/automation). Both do exactly the same work.

### Option A — Interactive mode

Run it with no arguments:

```bash
python -m cyclic_loading_analyzer
```

It will prompt you one question at a time. Example session:

```
Cyclic loading analyzer - interactive mode
(press Ctrl+C to cancel)

Input file (csv or xlsx): /home/me/Downloads/test_data.xlsx
Output xlsx file [default: /home/me/Downloads/test_data_results.xlsx]:
Stress reversal threshold: 10
Strain reversal threshold: 0.0005
Include the last (possibly incomplete) cycle? [yes/no, default no]: yes
```

- Press Enter on the output-file prompt to accept the suggested default
  (same folder as the input file, with `_results.xlsx` appended).
- Press Enter on the last-cycle prompt to accept the default (`no`).

When it finishes it prints a summary line, e.g.:

```
Wrote /home/me/Downloads/test_data_results.xlsx (30 stress cycles, 30 strain cycles, 160928 raw rows)
```

### Option B — Flag-based mode

```bash
python -m cyclic_loading_analyzer \
  --input data.csv \
  --output results.xlsx \
  --stress-threshold 10 \
  --strain-threshold 0.0005 \
  --show-last-cycle no
```

If you omit any of the required flags, the tool automatically falls back to
interactive mode and asks for the missing pieces.

### Arguments

| Flag | Required | Description |
|---|---|---|
| `--input` | yes | Path to the input file (`.csv` or `.xlsx`). |
| `--output` | yes | Path to the output `.xlsx` file to create. |
| `--stress-threshold` | yes | Reversal threshold for the Stress signal (same units as your Stress column). |
| `--strain-threshold` | yes | Reversal threshold for the Strain signal (same units as your Strain column). |
| `--show-last-cycle` | no | `yes`/`no`, default `no`. The final cycle in a test is often incomplete because the test stopped mid-cycle; set `yes` to keep it anyway (e.g. when you plan to append/compare against later, longer datasets). |
| `--interactive` | no | Force interactive prompts even if all flags above are also given. |

## Input file format — important

- Accepted formats: `.csv` or `.xlsx`.
- The tool reads **columns by position, not by header name**: column 1 is
  always treated as Time, column 2 as Stress, column 3 as Strain — whatever
  their header text says. Extra columns beyond the first three are ignored.
- **Check your actual column order before running.** Real export files do
  not always follow the Time/Stress/Strain order — for example one dataset
  used here had the columns as `time, strain, stress` (strain and stress
  swapped). If your column order isn't Time, Stress, Strain, reorder the
  columns yourself first (e.g. in Excel, or with a one-line pandas script)
  before feeding the file in — otherwise the tool will silently treat your
  Strain column as Stress and vice versa.

## Choosing thresholds

The threshold is the minimum reversal magnitude required to confirm a peak
or valley — pick it so it is:

- **well above** sensor noise / quantization steps in that column (so noise
  doesn't get mistaken for a reversal), and
- **well below** the actual peak-to-valley amplitude of a cycle (so a real
  reversal never gets missed).

Because Stress and Strain typically differ by orders of magnitude (e.g.
stress ~O(100), strain ~O(0.01)), they need separate, independently-scaled
thresholds — that's why the tool asks for both. If cycles look merged or
split in the output, revisit the threshold for that signal.

## Output workbook

- **Raw Data** — the original Time/Stress/Strain columns, full resolution, unmodified.
- **Stress Results** — one row per cycle: cycle #, time & value of the stress peak (Max columns A–C), cycle #, time & value of the stress valley (Min columns D–F).
- **Strain Results** — same layout, for strain.
- **Charts** — four native Excel charts:
  1. **Stress vs Time (with per-cycle Max & Min)** — the full raw Stress signal with the per-cycle Max and Min lines overlaid on top.
  2. **Strain vs Time (with per-cycle Max & Min)** — same, for Strain.
  3. **Stress Max & Min vs Time** — just the per-cycle Max/Min envelope on its own (no raw signal), useful for seeing cycle-to-cycle drift (e.g. cyclic hardening/softening, ratcheting) without the raw noise underneath.
  4. **Strain Max & Min vs Time** — same, for Strain.

  All charts are scatter-with-line (markers connected by straight lines).
  Raw-signal series beyond ~5,000 points are downsampled for chart
  responsiveness only — "Raw Data" and the peak/valley detection always use
  full-resolution data.

## Algorithm

Peak/valley detection is a hysteresis state machine run independently on
the Stress and Strain columns (each with its own threshold). While
extending in the current direction, the "new extreme" comparison is
**strict** (`>` / `<`), so that a plateau of repeated values at a true
peak/valley is recorded at its *first* occurrence, not its last. A reversal
is confirmed once the value has moved back by at least the threshold from
the running extreme. See [`cyclic_loading_analyzer/detector.py`](cyclic_loading_analyzer/detector.py)
for the exact implementation.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_detector.py` validates the algorithm against synthetic
triangular-wave data (clean cycles, noise below threshold, plateaued
peaks, small-magnitude strain-scale thresholds, and cycle numbering).

## Project layout

```
cyclic_loading_analyzer/
  detector.py       hysteresis peak/valley state machine + cycle pairing
  io_utils.py        input file reading (CSV/XLSX, positional columns)
  excel_writer.py     output workbook + chart construction
  cli.py              command-line entry point (flag-based + interactive)
tests/
  test_detector.py    self-tests on synthetic data
```

# cyclic-loading-analyzer

Reads cyclic loading test data (Time, Stress, Strain), detects the Max/Min
point of every loading cycle for both the Stress and Strain signals using a
hysteresis (threshold-reversal) filter, and writes a formatted Excel
workbook with the per-cycle results and native charts.

## Quick start (Windows 10)

Follow these steps in order, in **PowerShell**.

**1. Make sure Python is installed.** Open PowerShell and run:

```powershell
python --version
```

If that fails with "not recognized", either Python isn't installed, or it
wasn't added to PATH — install it from [python.org](https://www.python.org/downloads/)
and make sure to check **"Add Python to PATH"** during setup. If `python`
still isn't recognized afterwards, try `py` instead everywhere below.

**2. Open this project folder in PowerShell**, then create and activate a
virtual environment (a private, self-contained copy of the Python packages
this project needs — you only set this up once):

```powershell
cd cyclic-loading-analyzer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell refuses with *"running scripts is disabled on this
system"*, run this once and try activating again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Once activated, you'll see `(.venv)` at the start of the prompt line.

**3. Install the required packages** (only needed once per venv):

```powershell
pip install -r requirements.txt
```

**4. Put your raw data file(s) into the `raw_data` folder** inside this
project (each file must have Time, Stress, Strain as its first three
columns, in that order — see [Input file format](#input-file-format--important)
below). You can put more than one file in there — each is processed
independently.

**5. Run the analysis:**

```powershell
python run.py
```

For every `raw_data/<name>.xlsx` (or `.csv`), the output is written to
`results/<name>_result.xlsx`.

**Every time you come back later** (new PowerShell window), you only need
to repeat step 2's activation line (`.\.venv\Scripts\Activate.ps1`) before
step 5 — steps 1 and 3 are one-time setup.

> macOS/Linux users: the same steps apply, just replace
> `.\.venv\Scripts\Activate.ps1` with `source .venv/bin/activate`, and
> `python` with `python3` if needed.

## Requirements

- Python 3.9+
- pandas, numpy, openpyxl (installed via `requirements.txt`, see Quick start above)

## How the code works

This section is for anyone who wants more control than `run.py` gives
(different thresholds per run, a different input location, scripting it
into a pipeline) or just wants to understand what's happening under the
hood.

`run.py` (used in the Quick start above) is a thin wrapper — see
[Project layout](#project-layout) below. It processes every file in
`raw_data/` (one output per input in `results/`), auto-computes both
thresholds per file by default (see [Choosing thresholds](#choosing-thresholds)),
and always keeps the last cycle. Everything below describes the
underlying tool it calls, `cyclic_loading_analyzer`, which gives you a
choice for every setting on every run instead — including running it on
a single file at any path you want, not just `raw_data/`.

There are two ways to run it directly: **interactive** (it asks you
questions) or **flag-based** (you pass everything on the command line,
good for scripts/automation). Both do exactly the same work as `run.py`,
just with your own choice of input file, thresholds, and last-cycle
setting each time.

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
Stress reversal threshold [number, or leave blank to auto-compute]:
Strain reversal threshold [number, or leave blank to auto-compute]:
Include the last (possibly incomplete) cycle? [yes/no, default no]: yes
```

- Press Enter on the output-file prompt to accept the suggested default
  (same folder as the input file, with `_results.xlsx` appended).
- Press Enter on either threshold prompt to auto-compute it (see
  [Choosing thresholds](#choosing-thresholds)), or type a number to set it
  yourself.
- Press Enter on the last-cycle prompt to accept the default (`no`).

When it finishes it prints a summary line, e.g.:

```
Wrote /home/me/Downloads/test_data_results.xlsx (30 stress cycles [threshold 20.1], 30 strain cycles [threshold 0.00126], 160928 raw rows)
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

Omit `--input` or `--output` and the tool automatically falls back to
interactive mode and asks for them. Thresholds are optional — omit either
one (or pass `auto` explicitly) to auto-compute it instead.

### Arguments

| Flag | Required | Description |
|---|---|---|
| `--input` | yes | Path to the input file (`.csv` or `.xlsx`). |
| `--output` | yes | Path to the output `.xlsx` file to create. |
| `--stress-threshold` | no | Reversal threshold for the Stress signal (same units as your Stress column). Omit or pass `auto` to auto-compute it — see [Choosing thresholds](#choosing-thresholds). |
| `--strain-threshold` | no | Reversal threshold for the Strain signal (same units as your Strain column). Omit or pass `auto` to auto-compute it. |
| `--show-last-cycle` | no | `yes`/`no`, default `no`. The final cycle in a test is often incomplete because the test stopped mid-cycle; set `yes` to keep it anyway (e.g. when you plan to append/compare against later, longer datasets). |
| `--interactive` | no | Force interactive prompts even if all flags above are also given. |

## Input file format — important

- Accepted formats: `.csv` or `.xlsx`.
- **If the first three column headers are exactly "time", "stress" and
  "strain"** (case-insensitive, any order), the tool reorders them by name
  automatically — several real export files used here actually had the
  columns as `time, strain, stress` (strain and stress swapped), and this
  is corrected without you having to do anything.
- **For any other header text, columns are read by position**: column 1 is
  Time, column 2 Stress, column 3 Strain, regardless of what they're
  labeled. Extra columns beyond the first three are ignored.
- **If your headers don't spell out all three names**, double-check your
  actual column order before running — if it isn't Time, Stress, Strain,
  reorder the columns yourself first (e.g. in Excel, or with a one-line
  pandas script) before feeding the file in, otherwise the tool will
  silently treat the wrong column as Stress or Strain.

## Choosing thresholds

The threshold is the minimum reversal magnitude required to confirm a peak
or valley — pick it so it is:

- **well above** sensor noise / quantization steps in that column (so noise
  doesn't get mistaken for a reversal), and
- **well below** the actual peak-to-valley amplitude of a cycle (so a real
  reversal never gets missed).

Because Stress and Strain typically differ by orders of magnitude (e.g.
stress ~O(100), strain ~O(0.01)), they need separate, independently-scaled
thresholds.

**Auto-compute (the default in `run.py`, and in the interactive/flag modes
when a threshold is left blank / set to `auto`):** the threshold is set to
5% of that signal's own peak-to-peak range (`max - min`), computed
separately for Stress and for Strain. This scales automatically with each
file's amplitude, so the same setting works across datasets without manual
tuning — see `cyclic_loading_analyzer/detector.py::suggest_threshold`.

If cycles still look merged, split, or miscounted (e.g. Stress and Strain
report a different number of cycles for what should be the same physical
cycles), override it manually for that signal — a smaller fraction of the
range if reversals are being missed, larger if noise is being counted as
extra cycles.

## Isolated data-glitch filtering

Real test data occasionally has a single bad sample (a momentary DAQ error,
contact loss, etc.) that swings far enough to satisfy the threshold and
gets counted as a spurious extra Max/Min pair that isn't a genuine
peak/valley of the chart. After detection, the tool automatically checks
each confirmed Max against its neighboring Maxes (and each Min against its
neighboring Mins) and drops any that don't fit the local trend, using a
robust statistical test (a windowed Hampel filter) that tolerates a
smoothly ramping or decaying amplitude — see
`cyclic_loading_analyzer/detector.py::filter_spurious_extrema`.

**This never touches or discards any raw data** — "Raw Data" always
contains every original row unmodified. It only affects which points get
counted as cycle peaks/valleys in "Stress Results" / "Strain Results".
When something gets filtered, the CLI prints a line like:

```
  Filtered 1 spurious stress extrema and 0 spurious strain extrema (isolated data glitches, not real cycle peaks/valleys).
```

If it removes something that was actually real (or misses a real glitch),
adjust `window_radius` / `sensitivity` when calling `filter_spurious_extrema`
directly — the defaults were tuned against real test files with a genuine
isolated glitch and, separately, a real ambiguous step-change region that
should *not* be touched.

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
run.py                 simplest entry point: auto thresholds, batch-processes raw_data/ into results/
raw_data/               put your raw data file(s) here for run.py
results/                run.py writes <name>_result.xlsx here for each raw_data/<name> file
cyclic_loading_analyzer/
  detector.py           hysteresis peak/valley state machine + cycle pairing
  io_utils.py            input file reading (CSV/XLSX, positional columns)
  excel_writer.py         output workbook + chart construction
  cli.py                  command-line entry point (flag-based + interactive)
tests/
  test_detector.py        self-tests on synthetic data
```

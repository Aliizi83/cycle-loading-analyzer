# cyclic-loading-analyzer

Reads cyclic loading test data (Time, Stress, Strain), detects the
Max/Min point of every loading cycle for both the Stress and Strain
signals using a hysteresis (threshold-reversal) filter, and writes a
formatted Excel workbook with the results and native line charts.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m cyclic_loading_analyzer \
  --input data.csv \
  --output results.xlsx \
  --stress-threshold 5.0 \
  --strain-threshold 0.001 \
  --show-last-cycle no
```

### Arguments

| Flag | Required | Description |
|---|---|---|
| `--input` | yes | Path to input file (`.csv` or `.xlsx`). Column 1 = Time, column 2 = Stress, column 3 = Strain, regardless of header text. |
| `--output` | yes | Path to output `.xlsx` file. |
| `--stress-threshold` | yes | Reversal threshold for the Stress signal. |
| `--strain-threshold` | yes | Reversal threshold for the Strain signal. |
| `--show-last-cycle` | no | `yes`/`no`, default `no`. The final cycle can be incomplete since the test data may end mid-cycle. |

## Output workbook

- **Raw Data** — the original Time/Stress/Strain columns, full resolution.
- **Stress Results** — one row per cycle: cycle #, time & value of the stress peak, cycle #, time & value of the stress valley.
- **Strain Results** — same layout, for strain.
- **Charts** — Stress-vs-Time and Strain-vs-Time native Excel line charts, stacked vertically. Charts downsample beyond ~5,000 points for responsiveness; "Raw Data" and the peak/valley detection always use full resolution.

## Algorithm

Peak/valley detection is a hysteresis state machine run independently
on the Stress and Strain columns (each with its own threshold, since
their magnitudes typically differ by orders of magnitude). While
extending in the current direction, the "new extreme" comparison is
**strict** (`>` / `<`), so that a plateau of repeated values at a true
peak/valley is recorded at its *first* occurrence, not its last. A
reversal is confirmed once the value has moved back by at least the
threshold from the running extreme.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_detector.py` validates the algorithm against synthetic
triangular-wave data (clean, noisy below threshold, plateaued peaks,
and small-magnitude strain-scale thresholds).

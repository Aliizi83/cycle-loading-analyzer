"""Table of Stress-vs-Strain hysteresis-loop plots: files (rows) x cycle
number (columns).

    python plot_cycle_hysteresis_table.py 14 15 16 17 18
    python plot_cycle_hysteresis_table.py 19 20 21 22

Reads each raw_data file's own "Cycle" column directly (zero-crossing
based -- see cycle_labeling.py; already written into every raw_data file
by run.py) -- no recomputation. For each requested file x cycle column,
plots just that cycle's rows as Stress (Y axis) vs Strain (X axis),
tracing out that cycle's hysteresis loop.

Two column modes, auto-detected from the Cycle column's own values:

- Plain integer cycles (most files): 1, then every multiple of 5 up to
  the max cycle number needed across all requested files.
- Paired cycles (files 19-22, labeled "1_1"/"1_2"/"2_1"/"2_2"/... -- see
  cross_reference.paired_cycle_label): every "_2" (the second, closing
  half of each physical cycle) at odd pair numbers -- "1_2", "3_2",
  "5_2", "7_2", ... up to the max pair needed.

A batch must be all-plain or all-paired; mixing the two file kinds in
one call is refused, since they'd need different column axes.

Files can have different cycle counts, so the column list is based on
the MAX needed across all requested files; a file with fewer cycles
just leaves its later cells blank.

Output: raw_data_pictures/cycle_table_<first>-<last>.png -- one image,
high DPI, no size cap (each cell gets a fixed size, so the whole image
just grows with more files/cycles; zoom in as needed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator

PROJECT_DIR = Path(__file__).parent
RAW_DIR = PROJECT_DIR / "raw_data"
OUTPUT_DIR = PROJECT_DIR / "raw_data_pictures"

CELL_SIZE = 4.5  # inches per subplot
DPI = 200
STRAIN_SCALE = 100  # plotted as Strain * STRAIN_SCALE, labeled "Strain (x100)" -- fewer decimal digits to read

PAIRED_LABEL_RE = re.compile(r"^(\d+)_2$")


def _find_raw_path(number: int) -> Path:
    prefix = str(number)
    for p in RAW_DIR.glob(f"{prefix}*.xlsx"):
        rest = p.name[len(prefix) :]
        if rest and rest[0].isdigit():
            continue  # e.g. "160" shouldn't match number=16
        return p
    raise FileNotFoundError(f"No raw_data file found for {number!r} in {RAW_DIR}")


def _load_cycle_data(path: Path) -> tuple[pd.DataFrame, bool]:
    """Time/Cycle/Stress/Strain -- always the first 4 columns (the main
    Stress+Strain group), regardless of whether the file also has an
    Extension group after them. Returns (df, is_paired) -- is_paired is
    true if Cycle holds "N_1"/"N_2" labels rather than plain integers.
    """
    df = pd.read_excel(path).iloc[:, :4]
    df.columns = ["Time", "Cycle", "Stress", "Strain"]
    is_paired = df["Cycle"].astype(str).str.contains("_").any()
    if is_paired:
        df["Cycle"] = df["Cycle"].astype(str)
    else:
        df["Cycle"] = pd.to_numeric(df["Cycle"], errors="coerce")
    return df.dropna(subset=["Cycle"]), is_paired


def plot_table(file_numbers: list[int]) -> Path:
    data: dict[int, pd.DataFrame] = {}
    paired_flags = set()
    max_cycle = 0
    max_pair = 0
    for n in file_numbers:
        df, is_paired = _load_cycle_data(_find_raw_path(n))
        data[n] = df
        paired_flags.add(is_paired)
        if is_paired:
            pairs = [int(m.group(1)) for c in df["Cycle"].unique() if (m := PAIRED_LABEL_RE.match(c))]
            if pairs:
                max_pair = max(max_pair, max(pairs))
        elif len(df):
            max_cycle = max(max_cycle, int(df["Cycle"].max()))

    if len(paired_flags) > 1:
        raise SystemExit(
            "ERROR: mixing paired-cycle files (19-22) with plain-cycle files in one table is not supported "
            "-- they'd need different column axes."
        )
    is_paired = paired_flags.pop()

    columns: list[object]
    if is_paired:
        columns = [f"{p}_2" for p in range(1, max_pair + 1, 2)]
    else:
        columns = [1] + list(range(5, max_cycle + 1, 5))
    nrows, ncols = len(file_numbers), len(columns)

    fig, axes = plt.subplots(nrows, ncols, figsize=(CELL_SIZE * ncols, CELL_SIZE * nrows), squeeze=False)

    for i, n in enumerate(file_numbers):
        df = data[n]
        for j, cyc in enumerate(columns):
            ax = axes[i][j]
            sub = df[df["Cycle"] == cyc]
            if len(sub) == 0:
                ax.axis("off")
                continue
            ax.plot(sub["Strain"] * STRAIN_SCALE, sub["Stress"], color="#1F77B4", linewidth=0.8)
            ax.set_title(f"Cycle - {cyc}", fontsize=11)
            ax.set_xlabel(f"Strain (×{STRAIN_SCALE})")
            ax.set_ylabel("Stress (MPa)")
            ax.grid(True, alpha=0.3)

            # Origin at (0, 0): axes cross there instead of a bounding box,
            # and the visible range always includes 0 on both axes, even
            # if this cycle's own data doesn't naturally reach it -- makes
            # it easy to read the loop's position relative to zero.
            xmin, xmax = ax.get_xlim()
            ax.set_xlim(min(0, xmin), max(0, xmax))
            ymin, ymax = ax.get_ylim()
            ax.set_ylim(min(0, ymin), max(0, ymax))
            ax.spines["left"].set_position("zero")
            ax.spines["bottom"].set_position("zero")
            ax.spines["right"].set_visible(False)
            ax.spines["top"].set_visible(False)

            # Moving the spines to zero also drags their tick labels into
            # the middle of the plot -- with several closely-spaced decimal
            # ticks that runs them into each other (and into the axis
            # title). Fewer, wider-spaced ticks avoid the pile-up, and
            # pinning the axis titles at a fixed offset (not tied to where
            # the zero-spine happens to sit) keeps them from landing on
            # top of the tick numbers.
            ax.xaxis.set_major_locator(MaxNLocator(nbins=9, prune="both"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=9, prune="both"))
            ax.tick_params(axis="x", labelsize=8, pad=2)
            ax.tick_params(axis="y", labelsize=8, pad=2)
            ax.xaxis.set_label_coords(0.5, -0.08)
            ax.yaxis.set_label_coords(-0.12, 0.5)

    fig.suptitle("Stress vs Strain per cycle", fontsize=18, y=0.995)
    fig.tight_layout(rect=(0.03, 0, 1, 0.98))

    fig.canvas.draw()
    for i, n in enumerate(file_numbers):
        bbox = axes[i][0].get_position()
        y_center = (bbox.y0 + bbox.y1) / 2
        fig.text(0.008, y_center, f"Test - {n}", rotation=90, va="center", ha="left", fontsize=15, fontweight="bold")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"cycle_table_{file_numbers[0]}-{file_numbers[-1]}.png"
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
    return out_path


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python plot_cycle_hysteresis_table.py <file_number> [<file_number> ...]")
    file_numbers = [int(x) for x in sys.argv[1:]]
    out_path = plot_table(file_numbers)
    print(f"Saved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

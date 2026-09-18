"""Generate one PNG per raw_data file: a grid of Stress & Strain vs Time
charts, one subplot per correct_data ruler that file was combined with.

    python plot_corrected_grid.py <raw_data_number>

Reads the already-built raw_data_correct/<N>-<ruler>.xlsx files (see
build_corrected_raw_data_batch.py) -- no recomputation, just plots what's
already there. Each subplot shows that one file's Stress (blue, left
axis) and Strain (red, right axis) vs Time, same as the dual-axis chart
already embedded in each raw_data_correct file itself, but as a
matplotlib image so several rulers can be compared side by side in one
picture instead of one Excel file at a time.

Output: raw_data_correct_pictures/<N>.png
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_DIR = Path(__file__).parent
RAW_CORRECT_DIR = PROJECT_DIR / "raw_data_correct"
OUTPUT_DIR = PROJECT_DIR / "raw_data_correct_pictures"

CHART_MAX_POINTS = 5000  # downsample for plotting speed/file size, same as the Excel charts
STRESS_COLOR = "#1F77B4"  # blue
STRAIN_COLOR = "#C00000"  # red
NCOLS = 2


def find_files_for(raw_number: int) -> list[Path]:
    pattern = re.compile(rf"^{raw_number}-.+\.xlsx$")
    return sorted(p for p in RAW_CORRECT_DIR.glob(f"{raw_number}-*.xlsx") if pattern.match(p.name))


def _downsample(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    if n <= CHART_MAX_POINTS:
        return df
    step = n // CHART_MAX_POINTS + 1
    return df.iloc[::step]


def plot_grid(raw_number: int) -> Path:
    files = find_files_for(raw_number)
    if not files:
        raise SystemExit(f"No raw_data_correct files found for raw_data number {raw_number}")

    n = len(files)
    nrows = -(-n // NCOLS)  # ceil division

    fig, axes = plt.subplots(nrows, NCOLS, figsize=(9 * NCOLS, 4.5 * nrows))
    axes = axes.flatten() if n > 1 else [axes]

    for ax, path in zip(axes, files):
        df = pd.read_excel(path, usecols=["Time", "Stress", "Strain"])
        df = _downsample(df)

        ax2 = ax.twinx()
        ax.plot(df["Time"], df["Stress"], color=STRESS_COLOR, linewidth=0.8)
        ax2.plot(df["Time"], df["Strain"], color=STRAIN_COLOR, linewidth=0.8)

        ax.set_title(path.stem, fontsize=11)
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Stress (MPa)", color=STRESS_COLOR)
        ax2.set_ylabel("Strain", color=STRAIN_COLOR)
        ax.tick_params(axis="y", labelcolor=STRESS_COLOR)
        ax2.tick_params(axis="y", labelcolor=STRAIN_COLOR)
        ax.grid(True, alpha=0.3)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(f"raw_data {raw_number}: Stress & Strain vs Time, per ruler", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{raw_number}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python plot_corrected_grid.py <raw_data_number>")
    raw_number = int(sys.argv[1])
    out_path = plot_grid(raw_number)
    print(f"Saved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

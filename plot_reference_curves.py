"""Plot each correct_data file's own reference Stress-Strain curve.

    python plot_reference_curves.py

Uses the exact same curve-building logic as build_corrected_raw_data.py
(read_correct_data + build_lookup_curve, same DEFAULT_DECIMALS grouping)
so the plotted curve is exactly the function every raw_data row's Stress
gets looked up against -- not the raw scatter of points before grouping.

Output: correct_data_pictures/<stem>.png -- one per file in correct_data/,
including n-13.xlsx (the negative-side reference), even though it isn't
a selectable ruler on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from build_corrected_raw_data import CORRECT_DIR, DEFAULT_DECIMALS, _list_files, build_lookup_curve, read_correct_data

OUTPUT_DIR = Path(__file__).parent / "correct_data_pictures"


def plot_one(path: Path) -> Path:
    df = read_correct_data(path)
    curve_stress, curve_strain = build_lookup_curve(df, DEFAULT_DECIMALS)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(curve_stress, curve_strain, color="#1F77B4", linewidth=1)
    ax.set_xlabel("Stress (MPa)")
    ax.set_ylabel("Strain")
    ax.set_title(f"Reference curve: {path.stem}  ({len(curve_stress)} points, {DEFAULT_DECIMALS} decimals)")
    ax.grid(True, alpha=0.3)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{path.stem}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> int:
    files = _list_files(CORRECT_DIR)
    for path in files:
        out_path = plot_one(path)
        print(f"Saved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

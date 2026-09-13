"""Cross-reference tables: for each cycle's Max/Min in one signal, look up
the other two signals' values at (or nearest to) that same moment.

Stress and Strain share one Time column (same DAQ, same row) — reading
one at the other's cycle time is an exact index lookup, no matching
needed. A third signal (e.g. Extension, from an LVDT) has its own,
independently-sampled Time column, so any lookup involving it uses the
nearest available time instead.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .detector import Cycle


def nearest_index(target_time: float, time_array: np.ndarray) -> int:
    """Index of the sample in `time_array` closest to `target_time`."""
    idx = int(np.searchsorted(time_array, target_time))
    candidates = [i for i in (idx - 1, idx) if 0 <= i < len(time_array)]
    return min(candidates, key=lambda i: abs(time_array[i] - target_time))


def main_anchor_table(
    cycles: Sequence[Cycle],
    which: str,
    anchor_name: str,
    main_time: np.ndarray,
    other_values: np.ndarray,
    other_name: str,
    ext_time: np.ndarray,
    ext_values: np.ndarray,
    ext_name: str,
) -> list[dict]:
    """One row per cycle, anchored on a Stress or Strain Max/Min.

    The other main-group signal (Strain if anchor is Stress, or vice
    versa) is read at the exact same sample. The extension signal is
    read at its nearest available time to the anchor's.
    """
    rows = []
    for cycle in cycles:
        t = cycle.max_time if which == "max" else cycle.min_time
        v = cycle.max_value if which == "max" else cycle.min_value
        idx = int(np.searchsorted(main_time, t))
        ext_idx = nearest_index(t, ext_time)
        rows.append(
            {
                "Cycle": cycle.cycle_number,
                "Time": t,
                anchor_name: v,
                other_name: float(other_values[idx]),
                f"Time ({ext_name})": float(ext_time[ext_idx]),
                ext_name: float(ext_values[ext_idx]),
            }
        )
    return rows


def extension_anchor_table(
    cycles: Sequence[Cycle],
    which: str,
    ext_name: str,
    main_time: np.ndarray,
    stress: np.ndarray,
    strain: np.ndarray,
) -> list[dict]:
    """One row per cycle, anchored on an Extension Max/Min.

    Stress and Strain share one time base, so a single nearest-time
    lookup into it serves both.
    """
    rows = []
    for cycle in cycles:
        t = cycle.max_time if which == "max" else cycle.min_time
        v = cycle.max_value if which == "max" else cycle.min_value
        idx = nearest_index(t, main_time)
        rows.append(
            {
                "Cycle": cycle.cycle_number,
                "Time": t,
                ext_name: v,
                "Time (matched)": float(main_time[idx]),
                "Stress": float(stress[idx]),
                "Strain": float(strain[idx]),
            }
        )
    return rows


def build_cross_reference_tables(
    main_time: np.ndarray,
    stress: np.ndarray,
    strain: np.ndarray,
    stress_cycles: Sequence[Cycle],
    strain_cycles: Sequence[Cycle],
    ext_time: np.ndarray,
    ext_values: np.ndarray,
    ext_name: str,
    ext_cycles: Sequence[Cycle],
) -> dict[str, list[dict]]:
    """All 6 individual cross-reference tables, keyed by sheet name."""
    return {
        "Stress Max": main_anchor_table(
            stress_cycles, "max", "Stress", main_time, strain, "Strain", ext_time, ext_values, ext_name
        ),
        "Stress Min": main_anchor_table(
            stress_cycles, "min", "Stress", main_time, strain, "Strain", ext_time, ext_values, ext_name
        ),
        "Strain Max": main_anchor_table(
            strain_cycles, "max", "Strain", main_time, stress, "Stress", ext_time, ext_values, ext_name
        ),
        "Strain Min": main_anchor_table(
            strain_cycles, "min", "Strain", main_time, stress, "Stress", ext_time, ext_values, ext_name
        ),
        f"{ext_name} Max": extension_anchor_table(ext_cycles, "max", ext_name, main_time, stress, strain),
        f"{ext_name} Min": extension_anchor_table(ext_cycles, "min", ext_name, main_time, stress, strain),
    }

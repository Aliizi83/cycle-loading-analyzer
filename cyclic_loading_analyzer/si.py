"""Si parameter formulas.

Two different formulas are used, depending on the file (see run.py for
which files use which):

Zero-crossing (files 16, 17, 18) — Si anchored on the Stress signal's
descending zero crossing:

    Si = Extension - (strain_i * 70)

For each cycle already detected in the Stress signal (Max at max_time,
Min at min_time, with Max > 0 and Min < 0 — cycles that don't straddle
zero are skipped, since there's no descending zero-crossing to find):

1. Within the descending window [max_time, min_time], find the raw
   sample where Stress is closest to zero while still positive (the last
   point before it goes negative on the way down).
2. Read Strain at that same sample (strain_i) — same row, same file.
3. In the Extension signal's own (independently-sampled) Time column,
   find the closest Time to that same point and read Extension there.
4. Si = Extension - (strain_i * 70)

LVDT-max (files 19 and up) — Si anchored on the Extension (LVDT)
signal's own Max per cycle instead:

    Si = LVDT_max - (strain_at_LVDT_max_time * 70)

For each cycle detected in the Extension signal itself (its own
peak-to-peak Max, not a Stress zero-crossing):

1. Take that cycle's own Max value and Max time.
2. In the main Time column, find the closest Time to the LVDT Max time
   and read Strain there.
3. Si = LVDT_max - (strain_at_that_time * 70)
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from .detector import Cycle

CycleLabelFn = Callable[[int], object]

SiRow = tuple[object, float, float, float, float]


def _nearest_value(target_time: float, other_time: np.ndarray, other_value: np.ndarray) -> float:
    idx = np.searchsorted(other_time, target_time)
    candidates = [i for i in (idx - 1, idx) if 0 <= i < len(other_time)]
    best = min(candidates, key=lambda i: abs(other_time[i] - target_time))
    return float(other_value[best])


def _zero_crossing_strain(
    time: np.ndarray, stress: np.ndarray, strain: np.ndarray, max_time: float, min_time: float
) -> tuple[float, float] | None:
    """The last point before Stress crosses from positive to negative
    within [max_time, min_time] — closest to zero while still positive.

    Quantization can make several consecutive samples share the exact
    same minimum positive value (a plateau); plain argmin would return
    the FIRST of those tied samples, which can be a couple of samples
    earlier than the actual crossing. Take the LAST index tied for the
    minimum instead, since that's the one immediately before stress goes
    negative.
    """
    mask = (time >= max_time) & (time <= min_time)
    idxs = np.where(mask)[0]
    positive = idxs[stress[idxs] > 0]
    if len(positive) == 0:
        return None
    min_val = stress[positive].min()
    best = positive[stress[positive] == min_val][-1]
    return float(time[best]), float(strain[best])


def si_rows_zero_crossing(
    time: np.ndarray,
    stress: np.ndarray,
    strain: np.ndarray,
    stress_cycles: Sequence[Cycle],
    ext_time: np.ndarray,
    ext_value: np.ndarray,
) -> list[SiRow]:
    rows: list[SiRow] = []
    for cycle in stress_cycles:
        if cycle.max_value <= 0 or cycle.min_value >= 0:
            continue
        crossing = _zero_crossing_strain(time, stress, strain, cycle.max_time, cycle.min_time)
        if crossing is None:
            continue
        t_zero, strain_i = crossing
        ext_at_zero = _nearest_value(t_zero, ext_time, ext_value)
        si = (ext_at_zero) - (strain_i * 70)
        rows.append((cycle.cycle_number, t_zero, strain_i, ext_at_zero, si))
    return rows


def si_rows_lvdt_max(
    main_time: np.ndarray,
    strain: np.ndarray,
    ext_cycles: Sequence[Cycle],
    cycle_label_fn: CycleLabelFn | None,
) -> list[SiRow]:
    rows: list[SiRow] = []
    for cycle in ext_cycles:
        lvdt_max = cycle.max_value
        lvdt_max_time = cycle.max_time
        strain_i = _nearest_value(lvdt_max_time, main_time, strain)
        si = (lvdt_max) - (strain_i * 70)
        label = cycle_label_fn(cycle.cycle_number) if cycle_label_fn else cycle.cycle_number
        rows.append((label, lvdt_max_time, strain_i, lvdt_max, si))
    return rows

"""Per-row cycle number labeling.

Stress and Strain share one time base and physically cross zero every
cycle: a cycle spans zero -> Max -> zero -> Min -> zero, so its boundary
is the ascending zero-crossing (the last negative sample before the
signal rises past zero towards that cycle's Max) — wider than, and
offset from, the existing Max-to-following-Min "Cycle" pairing.

A signal that doesn't naturally cross zero (e.g. Extension from an LVDT)
can't use that rule, so its cycle boundaries are peak-to-peak instead:
each cycle's own Max time.

Every row gets a label: rows before the first boundary belong to cycle
1, rows past the last cycle's own window belong to the last cycle.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from .detector import Cycle


def _closest_to_zero_time(
    time: np.ndarray, values: np.ndarray, lo_time: float, hi_time: float, sign: str
) -> float | None:
    """Within [lo_time, hi_time], the time of the sample closest to zero
    while still `sign` ("positive" or "negative"), tie-broken to the LAST
    such sample — the one immediately before the actual crossing, since a
    quantization plateau can hold several samples at the same extreme
    value (see the identical rule used for the Stress zero-crossing in
    `compute_si.py`).
    """
    mask = (time >= lo_time) & (time <= hi_time)
    idxs = np.where(mask)[0]
    if len(idxs) == 0:
        return None
    if sign == "positive":
        candidates = idxs[values[idxs] > 0]
        if len(candidates) == 0:
            return None
        target = values[candidates].min()
    else:
        candidates = idxs[values[idxs] < 0]
        if len(candidates) == 0:
            return None
        target = values[candidates].max()
    best = candidates[values[candidates] == target][-1]
    return float(time[best])


def zero_crossing_boundaries(
    time: np.ndarray, values: np.ndarray, cycles: Sequence[Cycle]
) -> np.ndarray:
    """Ascending zero-crossing time marking the start of each cycle.

    Falls back to the previous cycle's Min time (or the start of the
    data, for the first cycle) if no crossing is found in that window
    (e.g. noisy data, or a cycle whose Min never actually goes negative).
    """
    boundaries = []
    prev_time = float(time[0])
    for cycle in cycles:
        crossing = _closest_to_zero_time(time, values, prev_time, cycle.max_time, "negative")
        boundaries.append(crossing if crossing is not None else prev_time)
        prev_time = cycle.min_time
    return np.array(boundaries, dtype=float)


def peak_to_peak_boundaries(cycles: Sequence[Cycle]) -> np.ndarray:
    """Each cycle's own Max time — used when a signal doesn't naturally
    cross zero, so an ascending-zero-crossing boundary isn't meaningful."""
    return np.array([c.max_time for c in cycles], dtype=float)


def assign_cycle_numbers(time: np.ndarray, boundaries: np.ndarray) -> np.ndarray:
    """1-based cycle number for every sample in `time`.

    `boundaries[i]` is the start of cycle i+1. Rows before the first
    boundary get cycle 1; rows past the last boundary get the last cycle
    number — every row gets a label, none are left blank.
    """
    n_cycles = len(boundaries)
    if n_cycles == 0:
        return np.ones(len(time), dtype=int)
    counts = np.searchsorted(boundaries, time, side="right")
    return np.clip(counts, 1, n_cycles)


def cycle_labels(
    time: np.ndarray,
    boundaries: np.ndarray,
    label_fn: Callable[[int], object] | None = None,
) -> np.ndarray:
    """Cycle number for every sample in `time`, or — with `label_fn`
    (e.g. `cross_reference.paired_cycle_label`) — a relabeled value like
    "1_1"/"1_2" instead of the plain integer.
    """
    numbers = assign_cycle_numbers(time, boundaries)
    if label_fn is None:
        return numbers
    n_cycles = len(boundaries) if len(boundaries) else int(numbers.max(initial=1))
    lookup = np.array([label_fn(n) for n in range(1, n_cycles + 1)], dtype=object)
    return lookup[numbers - 1]

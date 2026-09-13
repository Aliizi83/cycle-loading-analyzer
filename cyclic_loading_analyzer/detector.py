"""Hysteresis peak/valley detector for cyclic loading signals.

Implements the state-machine algorithm exactly as specified: the
"still extending in the same direction" comparisons are STRICT (> and <),
never >= or <=. Raw sensor data often repeats the same value for several
consecutive rows right at a true peak/valley (quantization noise /
plateau); strict comparisons make the algorithm record the FIRST
occurrence of that extreme value, not the last. This has been validated
against a confirmed reference dataset and must be preserved exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np

ExtremaType = Literal["Max", "Min"]

DEFAULT_THRESHOLD_FRACTION = 0.05


def suggest_threshold(values: Sequence[float], fraction: float = DEFAULT_THRESHOLD_FRACTION) -> float:
    """Suggest a hysteresis threshold as a fraction of the signal's peak-to-peak range.

    Scales automatically with each signal's own amplitude, so the same
    fraction works whether the column is stress (~O(100)) or strain
    (~O(0.01)) and across datasets with different amplitudes.
    """
    arr = np.asarray(values, dtype=float)
    return float((arr.max() - arr.min()) * fraction)


@dataclass(frozen=True)
class Extremum:
    time: float
    value: float
    kind: ExtremaType


def detect_extrema(
    time: Sequence[float], value: Sequence[float], threshold: float
) -> list[Extremum]:
    """Run the hysteresis reversal-detection state machine on one signal.

    Args:
        time: time values, same length as `value`.
        value: signal values (e.g. stress or strain).
        threshold: minimum reversal magnitude required to confirm a
            peak/valley.

    Returns:
        A list of confirmed Extremum entries, alternating Max, Min,
        Max, Min, ...
    """
    n = len(value)
    if n == 0:
        return []
    if len(time) != n:
        raise ValueError("time and value must have the same length")

    state = "UP"
    ext_val = value[0]
    ext_time = time[0]
    confirmed: list[Extremum] = []

    for i in range(1, n):
        v = value[i]
        t = time[i]
        if state == "UP":
            if v > ext_val:
                ext_val, ext_time = v, t
            elif ext_val - v >= threshold:
                confirmed.append(Extremum(ext_time, ext_val, "Max"))
                state = "DOWN"
                ext_val, ext_time = v, t
            # else: noise/tie -> candidate stays exactly as-is
        else:  # state == "DOWN"
            if v < ext_val:
                ext_val, ext_time = v, t
            elif v - ext_val >= threshold:
                confirmed.append(Extremum(ext_time, ext_val, "Min"))
                state = "UP"
                ext_val, ext_time = v, t

    return confirmed


DEFAULT_OUTLIER_WINDOW_RADIUS = 4
DEFAULT_OUTLIER_SENSITIVITY = 5.0


def filter_spurious_extrema(
    extrema: Sequence[Extremum],
    window_radius: int = DEFAULT_OUTLIER_WINDOW_RADIUS,
    sensitivity: float = DEFAULT_OUTLIER_SENSITIVITY,
) -> list[Extremum]:
    """Suppress confirmed extrema that break the local trend of their own type.

    Real sensor/DAQ glitches occasionally cause the raw signal to swing far
    enough to satisfy the hysteresis threshold, producing an extra Max/Min
    pair that doesn't represent a genuine top/bottom of the chart. This
    never touches the raw signal or `detect_extrema` — it only looks at the
    already-confirmed sequence and drops entries that don't fit their own
    local neighborhood (Max compared only to neighboring Maxes, Min to
    neighboring Mins).

    Uses a windowed Hampel identifier: for each point, compare it to the
    median of up to `window_radius` same-type neighbors on each side (a
    robust reference that tolerates a smoothly ramping/decaying amplitude,
    since one bad point can't drag a median off), and flag it if its
    deviation exceeds `sensitivity` robust standard deviations (via MAD) of
    that window. All points are evaluated independently from the original
    data in a single pass — deviations are never measured against a
    threshold derived from a list that's already had points removed, which
    would let one bad point inflate its own detection budget or cascade
    into discarding good points nearby.

    Removing an extremum can leave two same-type entries adjacent to each
    other (e.g. Max, Max with no Min between them); those are merged by
    keeping whichever is more extreme (the higher Max, or the lower Min)
    and dropping the other, since the pair together represented a single
    real peak/valley that the glitch briefly interrupted.
    """
    extrema = list(extrema)

    def outlier_positions(kind: ExtremaType) -> set[int]:
        idxs = [i for i, e in enumerate(extrema) if e.kind == kind]
        vals = np.array([extrema[i].value for i in idxs], dtype=float)
        n = len(vals)
        flagged = set()
        for j in range(n):
            lo, hi = max(0, j - window_radius), min(n, j + window_radius + 1)
            window = np.delete(vals[lo:hi], j - lo)
            if len(window) < 2:
                continue
            med = np.median(window)
            mad = np.median(np.abs(window - med))
            scale = 1.4826 * mad
            if scale == 0:
                continue
            if abs(vals[j] - med) > sensitivity * scale:
                flagged.add(idxs[j])
        return flagged

    to_remove = outlier_positions("Max") | outlier_positions("Min")
    filtered = [e for i, e in enumerate(extrema) if i not in to_remove]

    i = 0
    while i < len(filtered) - 1:
        if filtered[i].kind == filtered[i + 1].kind:
            if filtered[i].kind == "Max":
                keep = max(filtered[i], filtered[i + 1], key=lambda e: e.value)
            else:
                keep = min(filtered[i], filtered[i + 1], key=lambda e: e.value)
            filtered[i : i + 2] = [keep]
        else:
            i += 1

    return filtered


@dataclass(frozen=True)
class Cycle:
    cycle_number: int
    max_time: float
    max_value: float
    min_time: float
    min_value: float


def extrema_to_cycles(
    extrema: Sequence[Extremum], show_last_cycle: bool
) -> list[Cycle]:
    """Pair confirmed Max/Min extrema into cycles.

    `extrema` must alternate Max, Min, Max, Min, ... starting with Max
    (as produced by `detect_extrema`, which always starts in the "UP"
    state so the first confirmed extremum is a Max).

    Cycle k = the k-th Max paired with the k-th Min that follows it.
    If `show_last_cycle` is False, the final (Max, Min) pair is dropped
    since the last cycle may be incomplete / cut off at the end of the
    test.
    """
    cycles: list[Cycle] = []
    cycle_number = 0
    i = 0
    n = len(extrema)
    while i + 1 < n:
        first, second = extrema[i], extrema[i + 1]
        if first.kind != "Max" or second.kind != "Min":
            raise ValueError(
                "extrema must alternate Max, Min starting with Max; "
                f"got {first.kind} then {second.kind} at index {i}"
            )
        cycle_number += 1
        cycles.append(
            Cycle(
                cycle_number=cycle_number,
                max_time=first.time,
                max_value=first.value,
                min_time=second.time,
                min_value=second.value,
            )
        )
        i += 2

    if not show_last_cycle and cycles:
        cycles = cycles[:-1]

    return cycles

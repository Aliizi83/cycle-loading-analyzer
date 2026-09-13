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


def trailing_incomplete_extremum(
    time: Sequence[float], value: Sequence[float], confirmed: Sequence[Extremum]
) -> Extremum | None:
    """Best-effort completion of a final half-cycle that never confirmed.

    `detect_extrema` only records a peak/valley once the signal reverses by
    at least `threshold`. If the recording ends while still moving in one
    direction — never reversing far enough — the last confirmed extremum
    has no partner at all, even though the raw signal clearly kept
    climbing or falling after it. This looks at the raw samples strictly
    after the last confirmed extremum's time and returns the most extreme
    point reached there (the running minimum if the last confirmed entry
    was a Max, the running maximum if it was a Min) — exactly the value
    `detect_extrema`'s own state machine was tracking as an unconfirmed
    candidate when the array ran out.

    Returns `None` if there's nothing to complete: no confirmed extrema,
    or no samples after the last one.
    """
    if not confirmed:
        return None
    time = np.asarray(time, dtype=float)
    value = np.asarray(value, dtype=float)
    last = confirmed[-1]
    idx = np.searchsorted(time, last.time, side="right")
    if idx >= len(value):
        return None
    tail_value = value[idx:]
    tail_time = time[idx:]
    if last.kind == "Max":
        j = int(np.argmin(tail_value))
        kind: ExtremaType = "Min"
    else:
        j = int(np.argmax(tail_value))
        kind = "Max"
    return Extremum(float(tail_time[j]), float(tail_value[j]), kind)


DEFAULT_SECONDARY_REVERSAL_WINDOW = 8
DEFAULT_SECONDARY_REVERSAL_RATIO = 0.2


def merge_secondary_reversals(
    extrema: Sequence[Extremum],
    window: int = DEFAULT_SECONDARY_REVERSAL_WINDOW,
    ratio: float = DEFAULT_SECONDARY_REVERSAL_RATIO,
) -> list[Extremum]:
    """Remove brief secondary reversals nested inside one real half-cycle.

    Real cyclic tests occasionally show a fast, narrow reversal — a
    momentary partial unload/reload, a stress-relaxation blip, a brief
    dip right at a peak — that satisfies the hysteresis threshold and
    gets confirmed as its own Max/Min pair, even though it isn't a
    genuine top/bottom of the loading cycle. A genuine reversal, however
    small its amplitude, still takes roughly the same amount of TIME as
    its neighbors (the test machine's stroke rate doesn't change); these
    secondary blips complete in a small fraction of that time. This
    compares each segment's duration (time between consecutive confirmed
    extrema) to the local median duration of nearby segments — which
    naturally tracks the test's actual cadence, whether cycles are fast
    early in a ratcheting test or slow later — and removes the pair of
    extrema flanking any segment whose duration is disproportionately
    (< `ratio`) shorter than that local median. This never looks at the
    VALUE of an extremum, only timing, so a real cycle with unusually
    small or large amplitude relative to its neighbors is never touched
    (only a real value-based scan was tried first and it wrongly deleted
    a genuine reversal — validated against real test data before use).

    Removing a pair can leave two same-type entries adjacent (e.g. two
    Maxes with no Min between them, when the removed pair was a Min
    sandwiched between two nearly-equal peaks); those are merged by
    keeping whichever is more extreme, since together they represented
    one real peak/valley that the blip briefly interrupted.
    """
    extrema = list(extrema)

    def shortest_anomalous_segment() -> int | None:
        times = [e.time for e in extrema]
        durations = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        n = len(durations)
        best_idx, best_score = None, ratio
        for k in range(n):
            lo, hi = max(0, k - window), min(n, k + window + 1)
            neighbor = durations[lo:k] + durations[k + 1 : hi]
            if len(neighbor) < 3:
                continue
            local_median = float(np.median(neighbor))
            if local_median <= 0:
                continue
            score = durations[k] / local_median
            if score < best_score:
                best_idx, best_score = k, score
        return best_idx

    while len(extrema) >= 4:
        k = shortest_anomalous_segment()
        if k is None:
            break
        del extrema[k : k + 2]

        i = 0
        while i < len(extrema) - 1:
            if extrema[i].kind == extrema[i + 1].kind:
                if extrema[i].kind == "Max":
                    keep = max(extrema[i], extrema[i + 1], key=lambda e: e.value)
                else:
                    keep = min(extrema[i], extrema[i + 1], key=lambda e: e.value)
                extrema[i : i + 2] = [keep]
            else:
                i += 1

    return extrema


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

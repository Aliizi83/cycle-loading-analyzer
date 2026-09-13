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

ExtremaType = Literal["Max", "Min"]


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

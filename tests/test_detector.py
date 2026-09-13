"""Self-test using synthetic triangular-wave data with noise at the peaks."""

from __future__ import annotations

import numpy as np
import pytest

from cyclic_loading_analyzer.detector import (
    Extremum,
    detect_extrema,
    extrema_to_cycles,
    merge_secondary_reversals,
    trailing_incomplete_extremum,
)


def triangular_wave(n_cycles: int, points_per_half: int, amplitude: float, offset: float = 0.0):
    """Build a triangular wave: 0 -> amp -> 0 -> -amp -> 0 -> ... repeated."""
    up = np.linspace(0, amplitude, points_per_half, endpoint=False)
    down = np.linspace(amplitude, -amplitude, points_per_half, endpoint=False)
    up2 = np.linspace(-amplitude, 0, points_per_half, endpoint=False)
    one_cycle = np.concatenate([up, down, up2])
    wave = np.tile(one_cycle, n_cycles) + offset
    time = np.arange(len(wave), dtype=float)
    return time, wave


def test_clean_triangular_wave_stress():
    n_cycles = 5
    amplitude = 100.0
    time, stress = triangular_wave(n_cycles, points_per_half=20, amplitude=amplitude)
    threshold = 10.0

    extrema = detect_extrema(time, stress, threshold)
    kinds = [e.kind for e in extrema]

    assert kinds == ["Max", "Min"] * n_cycles
    for e in extrema:
        if e.kind == "Max":
            assert e.value == pytest.approx(amplitude, abs=1e-6)
        else:
            assert e.value == pytest.approx(-amplitude, abs=1e-6)

    cycles = extrema_to_cycles(extrema, show_last_cycle=True)
    assert len(cycles) == n_cycles

    cycles_dropped = extrema_to_cycles(extrema, show_last_cycle=False)
    assert len(cycles_dropped) == n_cycles - 1


def test_noise_smaller_than_threshold_is_ignored():
    """Small wiggles at/near the peak that don't exceed the threshold
    must not create spurious extra extrema."""
    n_cycles = 3
    amplitude = 50.0
    threshold = 5.0
    time, stress = triangular_wave(n_cycles, points_per_half=30, amplitude=amplitude)

    rng = np.random.default_rng(42)
    noise = rng.uniform(-threshold * 0.5, threshold * 0.5, size=stress.shape)
    noisy_stress = stress + noise

    extrema = detect_extrema(time, noisy_stress, threshold)
    kinds = [e.kind for e in extrema]
    assert kinds == ["Max", "Min"] * n_cycles


def test_plateau_at_peak_records_first_occurrence():
    """A run of identical values at the true peak must be recorded at
    its FIRST occurrence (strict > / < comparisons), not its last."""
    time = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
    # rises to 10, plateaus at 10 for 3 samples (t=2,3,4), then falls
    value = np.array([0, 5, 10, 10, 10, 5, 0, -5, -10], dtype=float)
    threshold = 4.0

    extrema = detect_extrema(time, value, threshold)
    assert len(extrema) >= 1
    first_max = extrema[0]
    assert first_max.kind == "Max"
    assert first_max.value == 10
    assert first_max.time == 2.0  # first occurrence, not t=3 or t=4


def test_strain_independent_threshold_small_magnitude():
    """Strain values are ~O(0.01); a small threshold appropriate to
    that scale must still correctly detect cycles."""
    n_cycles = 4
    amplitude = 0.02
    threshold = 0.002
    time, strain = triangular_wave(n_cycles, points_per_half=15, amplitude=amplitude)

    extrema = detect_extrema(time, strain, threshold)
    kinds = [e.kind for e in extrema]
    assert kinds == ["Max", "Min"] * n_cycles
    for e in extrema:
        expected = amplitude if e.kind == "Max" else -amplitude
        assert e.value == pytest.approx(expected, abs=1e-9)


def test_cycle_pairing_and_numbering():
    time = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    value = np.array([0, 10, 0, 10, 0, 10], dtype=float)  # Max,Min,Max,Min,Max
    threshold = 5.0

    extrema = detect_extrema(time, value, threshold)
    cycles = extrema_to_cycles(extrema, show_last_cycle=True)

    assert [c.cycle_number for c in cycles] == list(range(1, len(cycles) + 1))
    for c in cycles:
        assert c.max_value == 10
        assert c.min_value == 0


def test_empty_input():
    assert detect_extrema([], [], 1.0) == []


def test_trailing_incomplete_extremum_after_max_finds_running_min():
    """Recording ends mid-descent (never reverses far enough to confirm a
    Min) — the true test-25 scenario: the last confirmed extremum is a Max
    and the tail keeps falling all the way to the last sample."""
    time = np.array([0, 1, 2, 3, 4, 5, 6], dtype=float)
    value = np.array([0, 10, 5, 3, 4, 2, 1], dtype=float)  # Max confirmed at t=1 (10)
    confirmed = detect_extrema(time, value, threshold=6.0)
    assert confirmed == [Extremum(1.0, 10.0, "Max")]

    trailing = trailing_incomplete_extremum(time, value, confirmed)

    assert trailing == Extremum(6.0, 1.0, "Min")  # lowest point after t=1


def test_trailing_incomplete_extremum_after_min_finds_running_max():
    time = np.array([0, 1, 2, 3, 4, 5, 6], dtype=float)
    value = np.array([0, 10, 0, 3, 8, 4, 9], dtype=float)  # Max at t=1, Min at t=2
    confirmed = detect_extrema(time, value, threshold=6.0)
    assert confirmed == [Extremum(1.0, 10.0, "Max"), Extremum(2.0, 0.0, "Min")]

    trailing = trailing_incomplete_extremum(time, value, confirmed)

    assert trailing == Extremum(6.0, 9.0, "Max")  # highest point after t=2


def test_trailing_incomplete_extremum_none_when_nothing_confirmed():
    assert trailing_incomplete_extremum([0.0, 1.0], [0.0, 1.0], []) is None


def test_trailing_incomplete_extremum_none_when_confirmed_is_last_sample():
    # a confirmed extremum sitting exactly on the final sample has no tail
    # left to complete from (detect_extrema itself can't actually produce
    # this — confirmation always happens on a later sample than the peak —
    # but the function should still handle it safely if it ever occurs).
    time = np.array([0.0, 1.0, 2.0])
    value = np.array([5.0, 10.0, 3.0])
    confirmed = [Extremum(2.0, 3.0, "Min")]
    assert trailing_incomplete_extremum(time, value, confirmed) is None


def _regular_cycle_extrema(n_cycles: int, period: float = 1.0, max_val: float = 10.0, min_val: float = -10.0):
    """A clean, evenly-spaced Max/Min sequence with no anomalies."""
    extrema = []
    t = 0.0
    for _ in range(n_cycles):
        t += period / 2
        extrema.append(Extremum(t, max_val, "Max"))
        t += period / 2
        extrema.append(Extremum(t, min_val, "Min"))
    return extrema


def test_merge_secondary_reversals_leaves_clean_cycles_unchanged():
    extrema = _regular_cycle_extrema(15)
    assert merge_secondary_reversals(extrema) == extrema


def test_merge_secondary_reversals_removes_isolated_fast_blip():
    """Reproduces the real case (file 21/17): a genuine but very fast
    (~5% of normal half-cycle duration) secondary reversal nested inside
    an otherwise-smooth descending leg, with an amplitude comfortably
    above the detection threshold so it got confirmed. Must be removed
    without touching the real cycles around it."""
    extrema = _regular_cycle_extrema(10, period=1.0)
    # locate a Max at t=5.5 (start of a descending leg toward Min at t=6.0)
    max_idx = next(i for i, e in enumerate(extrema) if e.time == 5.5)
    min_idx = max_idx + 1
    assert extrema[min_idx] == Extremum(6.0, -10.0, "Min")
    blip_min = Extremum(5.53, -2.0, "Min")
    blip_max = Extremum(5.56, -1.5, "Max")
    extrema_with_blip = extrema[: min_idx] + [blip_min, blip_max] + extrema[min_idx:]

    result = merge_secondary_reversals(extrema_with_blip)

    assert result == extrema  # blip fully removed, real cycles untouched


def test_merge_secondary_reversals_removes_clustered_blip_at_a_peak():
    """Reproduces the real case (file 24/27): a brief dip-and-recover right
    at a peak splits one real Max into two near-identical Maxes with a
    shallow spurious Min between them. The later (larger) Max should
    survive, matching what's observed in the real data."""
    extrema = _regular_cycle_extrema(10, period=1.0)
    max_idx = next(i for i, e in enumerate(extrema) if e.time == 5.5)
    real_max = extrema[max_idx]
    extrema_with_blip = (
        extrema[:max_idx]
        + [Extremum(real_max.time, real_max.value, "Max"), Extremum(5.51, 9.0, "Min"), Extremum(5.52, 10.1, "Max")]
        + extrema[max_idx + 1 :]
    )

    result = merge_secondary_reversals(extrema_with_blip)

    kinds = [e.kind for e in result]
    assert kinds == ["Max", "Min"] * (len(result) // 2)
    times = [e.time for e in result]
    assert 9.0 not in [e.value for e in result]
    assert 5.5 not in times  # the earlier, shallower peak of the pair was dropped
    assert Extremum(5.52, 10.1, "Max") in result  # the later, higher peak survives


def test_merge_secondary_reversals_needs_at_least_four_extrema():
    extrema = [Extremum(0.0, 10.0, "Max"), Extremum(1.0, -10.0, "Min")]
    assert merge_secondary_reversals(extrema) == extrema


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

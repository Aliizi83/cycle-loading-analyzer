"""Self-test using synthetic triangular-wave data with noise at the peaks."""

from __future__ import annotations

import numpy as np
import pytest

from cyclic_loading_analyzer.detector import (
    Extremum,
    detect_extrema,
    extrema_to_cycles,
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

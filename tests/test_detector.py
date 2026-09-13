"""Self-test using synthetic triangular-wave data with noise at the peaks."""

from __future__ import annotations

import numpy as np
import pytest

from cyclic_loading_analyzer.detector import (
    Extremum,
    detect_extrema,
    extrema_to_cycles,
    filter_spurious_extrema,
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


def test_filter_spurious_extrema_leaves_clean_ramp_unchanged():
    """A smoothly ramping-amplitude cycle sequence (no glitches) must pass through untouched."""
    extrema = [
        Extremum(0.25, 53.0, "Max"),
        Extremum(0.37, -3.3, "Min"),
        Extremum(0.52, 78.6, "Max"),
        Extremum(0.68, -3.9, "Min"),
        Extremum(0.89, 105.1, "Max"),
        Extremum(1.09, -4.2, "Min"),
        Extremum(1.35, 131.5, "Max"),
        Extremum(1.60, -4.5, "Min"),
    ]
    assert filter_spurious_extrema(extrema) == extrema


def test_filter_spurious_extrema_removes_isolated_glitch():
    """Reproduces the real-world case (a ratcheting test with steadily
    growing amplitude): a single bad sample creates a false Min sandwiched
    between two Maxes that are otherwise consistent with each other and
    the surrounding trend. Needs enough surrounding cycles for the local
    window to have real trend context — a handful of points either side
    of the glitch isn't representative of how this runs on real data."""
    n_cycles = 20
    max_trend = np.linspace(100, 500, n_cycles)
    min_trend = np.linspace(-10, -80, n_cycles)
    extrema = []
    for i in range(n_cycles):
        extrema.append(Extremum(float(2 * i), max_trend[i], "Max"))
        extrema.append(Extremum(float(2 * i + 1), min_trend[i], "Min"))

    glitch_idx = 2 * (n_cycles // 2) + 1  # a Min entry, mid-sequence
    good_value = extrema[glitch_idx].value
    extrema[glitch_idx] = Extremum(extrema[glitch_idx].time, 250.0, "Min")  # the glitch

    filtered = filter_spurious_extrema(extrema)

    kinds = [e.kind for e in filtered]
    assert kinds == ["Max", "Min"] * (len(filtered) // 2)
    values = [e.value for e in filtered]
    assert 250.0 not in values
    # the two Maxes flanking the glitch must have merged into one, keeping
    # the more extreme (higher) value
    flanking_max = max(
        max_trend[n_cycles // 2], max_trend[n_cycles // 2 + 1]
    )
    assert flanking_max in values
    assert values.count(flanking_max) == 1
    # every genuine min elsewhere in the trend must survive untouched
    assert good_value not in values  # it was replaced by the glitch, not recoverable
    for v in min_trend:
        if v != good_value:
            assert v in values


def test_filter_spurious_extrema_requires_at_least_three_of_a_kind():
    """With fewer than 3 Max (or Min) points there's no local trend to
    compare against, so nothing should be removed."""
    extrema = [
        Extremum(0.0, 100.0, "Max"),
        Extremum(1.0, -999.0, "Min"),
        Extremum(2.0, 100.0, "Max"),
    ]
    assert filter_spurious_extrema(extrema) == extrema


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

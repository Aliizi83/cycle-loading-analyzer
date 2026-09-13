"""Tests for input-file column handling."""

from __future__ import annotations

import pandas as pd

from cyclic_loading_analyzer.io_utils import read_raw_data


def test_reorders_when_headers_unambiguously_name_all_three(tmp_path):
    path = tmp_path / "swapped.csv"
    pd.DataFrame({"time": [0, 1], "strain": [0.01, 0.02], "stress": [100, 200]}).to_csv(
        path, index=False
    )

    df = read_raw_data(path)

    assert list(df.columns) == ["Time", "Stress", "Strain"]
    assert df["Stress"].tolist() == [100, 200]
    assert df["Strain"].tolist() == [0.01, 0.02]


def test_positional_fallback_for_unrecognized_headers(tmp_path):
    path = tmp_path / "generic.csv"
    pd.DataFrame({"col_a": [0, 1], "col_b": [100, 200], "col_c": [0.01, 0.02]}).to_csv(
        path, index=False
    )

    df = read_raw_data(path)

    assert list(df.columns) == ["Time", "Stress", "Strain"]
    assert df["Stress"].tolist() == [100, 200]
    assert df["Strain"].tolist() == [0.01, 0.02]


def test_positional_when_headers_partially_match(tmp_path):
    """Only 'time' matches a known label; must NOT trigger name-based reordering."""
    path = tmp_path / "partial.csv"
    pd.DataFrame({"time": [0, 1], "sigma": [100, 200], "epsilon": [0.01, 0.02]}).to_csv(
        path, index=False
    )

    df = read_raw_data(path)

    assert df["Stress"].tolist() == [100, 200]
    assert df["Strain"].tolist() == [0.01, 0.02]

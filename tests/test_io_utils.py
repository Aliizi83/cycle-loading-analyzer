"""Tests for input-file column handling."""

from __future__ import annotations

import pandas as pd

from cyclic_loading_analyzer.io_utils import peek_column_count, read_raw_data, read_single_signal_data


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


def test_peek_column_count(tmp_path):
    path = tmp_path / "two_col.csv"
    pd.DataFrame({"time": [0, 1], "extension": [0.04, 0.05]}).to_csv(path, index=False)

    assert peek_column_count(path) == 2


def test_read_single_signal_data_keeps_original_header(tmp_path):
    path = tmp_path / "lvdt.csv"
    pd.DataFrame({"time": [0.0, 0.1, 0.2], "extension": [0.04, 0.05, 0.07]}).to_csv(
        path, index=False
    )

    df, signal_name = read_single_signal_data(path)

    assert signal_name == "extension"
    assert list(df.columns) == ["Time", "extension"]
    assert df["extension"].tolist() == [0.04, 0.05, 0.07]


def test_read_single_signal_data_ignores_extra_columns(tmp_path):
    path = tmp_path / "extra.csv"
    pd.DataFrame(
        {"time": [0.0, 0.1], "extension": [0.04, 0.05], "notes": ["a", "b"]}
    ).to_csv(path, index=False)

    df, signal_name = read_single_signal_data(path)

    assert signal_name == "extension"
    assert list(df.columns) == ["Time", "extension"]

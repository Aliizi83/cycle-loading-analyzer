"""Excel workbook output: Raw Data, one Results sheet per signal, Charts."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .detector import Cycle

CHART_MAX_POINTS = 5000
HEADER_FONT = Font(bold=True)
TITLE_FONT = Font(bold=True, size=12)
CENTER = Alignment(horizontal="center", vertical="center")

RAW_SERIES_COLOR = "1F77B4"  # blue
MAX_SERIES_COLOR = "C00000"  # red
MIN_SERIES_COLOR = "FFC000"  # amber (more legible than pure yellow on white)


def _write_raw_data_sheet(wb: Workbook, raw_df: pd.DataFrame) -> Worksheet:
    ws = wb.create_sheet("Raw Data")
    headers = list(raw_df.columns)
    ws.append(headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
    for row in raw_df.itertuples(index=False):
        ws.append(list(row))
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14
    ws.freeze_panes = "A2"
    return ws


def _write_results_sheet(
    wb: Workbook, sheet_name: str, cycles: Sequence[Cycle]
) -> Worksheet:
    ws = wb.create_sheet(sheet_name)

    ws.merge_cells("A1:C1")
    ws["A1"] = "Max"
    ws.merge_cells("D1:F1")
    ws["D1"] = "Min"
    for coord in ("A1", "D1"):
        ws[coord].font = TITLE_FONT
        ws[coord].alignment = CENTER

    headers = ["Cycle", "Time", "Max", "Cycle", "Time", "Min"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.alignment = CENTER

    for row_offset, cycle in enumerate(cycles, start=3):
        ws.cell(row=row_offset, column=1, value=cycle.cycle_number)
        ws.cell(row=row_offset, column=2, value=cycle.max_time)
        ws.cell(row=row_offset, column=3, value=cycle.max_value)
        ws.cell(row=row_offset, column=4, value=cycle.cycle_number)
        ws.cell(row=row_offset, column=5, value=cycle.min_time)
        ws.cell(row=row_offset, column=6, value=cycle.min_value)

    for col_idx in range(1, 7):
        ws.column_dimensions[get_column_letter(col_idx)].width = 12
    ws.freeze_panes = "A3"
    return ws


def _add_charts_sheet(
    wb: Workbook, raw_df: pd.DataFrame, signals: Sequence[tuple[str, Sequence[Cycle]]]
) -> Worksheet:
    ws = wb.create_sheet("Charts")
    raw_ws = wb["Raw Data"]
    n_rows = len(raw_df)
    n_cols = raw_df.shape[1]

    # Downsample only the chart *series* reference for large datasets;
    # "Raw Data" itself always stays full resolution.
    step = max(1, (n_rows // CHART_MAX_POINTS) + 1) if n_rows > CHART_MAX_POINTS else 1

    last_row = n_rows + 1  # +1 for header row

    if step == 1:
        source_ws = raw_ws
        source_last_row = last_row
    else:
        # Reference() cannot stride rows, so downsampled chart series
        # are built from a hidden helper sheet with every Nth raw row.
        helper = wb.create_sheet("_chart_data")
        helper.sheet_state = "hidden"
        helper.append(list(raw_df.columns))
        for r in range(2, last_row + 1, step):
            helper.append([raw_ws.cell(row=r, column=c).value for c in range(1, n_cols + 1)])
        source_ws = helper
        source_last_row = helper.max_row

    def add_raw_series(chart: ScatterChart, y_col: int) -> None:
        xvalues = Reference(source_ws, min_col=1, min_row=2, max_row=source_last_row)
        yvalues = Reference(source_ws, min_col=y_col, min_row=1, max_row=source_last_row)
        series = Series(yvalues, xvalues, title_from_data=True)
        series.marker.symbol = "none"
        series.smooth = False
        series.graphicalProperties.line.width = 9000
        series.graphicalProperties.line.solidFill = RAW_SERIES_COLOR
        chart.series.append(series)

    def add_max_min_series(chart: ScatterChart, results_ws: Worksheet, n_cycles: int) -> None:
        if n_cycles == 0:
            return
        last_row = 2 + n_cycles
        # Max: Time in col B, value in col C (red). Min: Time in col E, value in col F (amber).
        for x_col, y_col, color in ((2, 3, MAX_SERIES_COLOR), (5, 6, MIN_SERIES_COLOR)):
            xvalues = Reference(results_ws, min_col=x_col, min_row=3, max_row=last_row)
            yvalues = Reference(results_ws, min_col=y_col, min_row=2, max_row=last_row)
            series = Series(yvalues, xvalues, title_from_data=True)
            series.marker.symbol = "circle"
            series.marker.size = 6
            series.marker.graphicalProperties.solidFill = color
            series.marker.graphicalProperties.line.solidFill = color
            series.smooth = False
            series.graphicalProperties.line.width = 15000
            series.graphicalProperties.line.solidFill = color
            chart.series.append(series)

    def make_chart(
        title: str,
        y_label: str,
        *,
        raw_y_col: int | None,
        results_ws: Worksheet,
        n_cycles: int,
    ) -> ScatterChart:
        chart = ScatterChart()
        chart.title = title
        chart.style = 13
        chart.x_axis.title = "Time"
        chart.y_axis.title = y_label
        chart.width = 24
        chart.height = 12
        if raw_y_col is not None:
            add_raw_series(chart, raw_y_col)
        add_max_min_series(chart, results_ws, n_cycles)
        chart.legend.position = "b"
        chart.legend.overlay = False
        return chart

    combined_charts = []
    maxmin_charts = []
    for i, (name, _cycles) in enumerate(signals):
        raw_y_col = i + 2  # column A=Time; first signal is B, second is C, ...
        results_ws = wb[f"{name} Results"]
        n_cycles = max(0, results_ws.max_row - 2)
        combined_charts.append(
            make_chart(
                f"{name} vs Time (with per-cycle Max & Min)",
                name,
                raw_y_col=raw_y_col,
                results_ws=results_ws,
                n_cycles=n_cycles,
            )
        )
        maxmin_charts.append(
            make_chart(
                f"{name} Max & Min vs Time",
                name,
                raw_y_col=None,
                results_ws=results_ws,
                n_cycles=n_cycles,
            )
        )

    row = 1
    for chart in combined_charts + maxmin_charts:
        ws.add_chart(chart, f"A{row}")
        row += 25

    return ws


def write_workbook(
    output_path: str | Path,
    raw_df: pd.DataFrame,
    signals: Sequence[tuple[str, Sequence[Cycle]]],
) -> None:
    """Write Raw Data, one Results sheet per signal, and Charts.

    `raw_df` columns must be ["Time", <signal 1 name>, <signal 2 name>, ...]
    matching the names given in `signals`, in the same order. Two charts
    are produced per signal (raw-with-overlay, and Max/Min-only) — e.g. 2
    charts total for one signal, 4 for two.
    """
    wb = Workbook()
    wb.remove(wb.active)  # drop default empty sheet

    _write_raw_data_sheet(wb, raw_df)
    for name, cycles in signals:
        _write_results_sheet(wb, f"{name} Results", cycles)
    _add_charts_sheet(wb, raw_df, signals)

    wb.save(str(output_path))

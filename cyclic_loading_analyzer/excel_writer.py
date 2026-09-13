"""Excel workbook output: Raw Data, Stress/Strain Results, Charts."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .detector import Cycle

CHART_MAX_POINTS = 5000
HEADER_FONT = Font(bold=True)
TITLE_FONT = Font(bold=True, size=12)
CENTER = Alignment(horizontal="center", vertical="center")


def _write_raw_data_sheet(wb: Workbook, df: pd.DataFrame) -> Worksheet:
    ws = wb.create_sheet("Raw Data")
    ws.append(["Time", "Stress", "Strain"])
    for cell in ws[1]:
        cell.font = HEADER_FONT
    for row in df.itertuples(index=False):
        ws.append([row.Time, row.Stress, row.Strain])
    for col in "ABC":
        ws.column_dimensions[col].width = 14
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


def _add_charts_sheet(wb: Workbook, n_rows: int) -> Worksheet:
    ws = wb.create_sheet("Charts")
    raw_ws = wb["Raw Data"]

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
        helper.append(["Time", "Stress", "Strain"])
        for r in range(2, last_row + 1, step):
            helper.append(
                [
                    raw_ws.cell(row=r, column=1).value,
                    raw_ws.cell(row=r, column=2).value,
                    raw_ws.cell(row=r, column=3).value,
                ]
            )
        source_ws = helper
        source_last_row = helper.max_row

    def make_chart(title: str, y_col: int) -> LineChart:
        chart = LineChart()
        chart.title = title
        chart.x_axis.title = "Time"
        chart.y_axis.title = title.split(" vs ")[0]
        chart.style = 2
        chart.width = 24
        chart.height = 12
        data = Reference(source_ws, min_col=y_col, min_row=1, max_row=source_last_row)
        cats = Reference(source_ws, min_col=1, min_row=2, max_row=source_last_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        return chart

    stress_chart = make_chart("Stress vs Time", 2)
    strain_chart = make_chart("Strain vs Time", 3)

    ws.add_chart(stress_chart, "A1")
    ws.add_chart(strain_chart, "A26")
    return ws


def write_workbook(
    output_path: str | Path,
    raw_df: pd.DataFrame,
    stress_cycles: Sequence[Cycle],
    strain_cycles: Sequence[Cycle],
) -> None:
    wb = Workbook()
    wb.remove(wb.active)  # drop default empty sheet

    _write_raw_data_sheet(wb, raw_df)
    _write_results_sheet(wb, "Stress Results", stress_cycles)
    _write_results_sheet(wb, "Strain Results", strain_cycles)
    _add_charts_sheet(wb, n_rows=len(raw_df))

    wb.save(str(output_path))

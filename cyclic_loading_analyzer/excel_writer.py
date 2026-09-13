"""Excel workbook output: Raw Data, one Results sheet per signal, Charts.

Signals are organized into groups that share one Time column (e.g. Stress
and Strain, sampled by the same DAQ). A workbook can have more than one
group with independent time bases and row counts (e.g. a second group for
an LVDT-sampled Extension signal) — each still gets its own pair of
charts, all landing in the same "Charts" sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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


@dataclass(frozen=True)
class SignalGroup:
    """One or more signals sharing a single Time column.

    `time` is that shared time base. `signals` is a list of
    (name, values, cycles) — `values` is the raw signal aligned to `time`
    (same length), `cycles` are its already-detected Max/Min pairs.
    """

    time: Sequence[float]
    signals: Sequence[tuple[str, Sequence[float], Sequence[Cycle]]]


def _write_raw_data_sheet(
    wb: Workbook, groups: Sequence[SignalGroup]
) -> tuple[Worksheet, list[tuple[int, list[int], int]]]:
    """Write each group as its own block of columns (Time, signal...),
    left to right, separated by one blank spacer column. Groups may have
    different row counts — shorter ones just leave blank cells below
    their own last row.

    Returns (worksheet, layout) where layout[i] = (time_col, value_cols,
    n_rows) for groups[i], all 1-indexed column numbers.
    """
    ws = wb.create_sheet("Raw Data")

    layout: list[tuple[int, list[int], int]] = []
    header_row: list[str] = []
    col = 1
    for gi, group in enumerate(groups):
        time_col = col
        value_cols = []
        header_row.append("Time")
        col += 1
        for name, _values, _cycles in group.signals:
            header_row.append(name)
            value_cols.append(col)
            col += 1
        layout.append((time_col, value_cols, len(group.time)))
        if gi < len(groups) - 1:
            header_row.append("")  # spacer column
            col += 1

    ws.append(header_row)
    for cell in ws[1]:
        if cell.value:
            cell.font = HEADER_FONT

    max_rows = max((n for _, _, n in layout), default=0)
    for r in range(max_rows):
        row: list[object] = []
        for gi, group in enumerate(groups):
            _time_col, value_cols, n_rows = layout[gi]
            if r < n_rows:
                row.append(group.time[r])
                for vi, (_name, values, _cycles) in enumerate(group.signals):
                    row.append(values[r])
            else:
                row.append(None)
                row.extend([None] * len(group.signals))
            if gi < len(groups) - 1:
                row.append(None)  # spacer
        ws.append(row)

    for col_idx in range(1, len(header_row) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14
    ws.freeze_panes = "A2"
    return ws, layout


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
    wb: Workbook,
    groups: Sequence[SignalGroup],
    layout: list[tuple[int, list[int], int]],
) -> Worksheet:
    ws = wb.create_sheet("Charts")
    raw_ws = wb["Raw Data"]
    helper_ws = None  # created lazily, only if some group needs downsampling

    def add_raw_series(chart: ScatterChart, source_ws: Worksheet, x_col: int, y_col: int, last_row: int) -> None:
        xvalues = Reference(source_ws, min_col=x_col, min_row=2, max_row=last_row)
        yvalues = Reference(source_ws, min_col=y_col, min_row=1, max_row=last_row)
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
        raw_source: tuple[Worksheet, int, int, int] | None,
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
        if raw_source is not None:
            source_ws, x_col, y_col, last_row = raw_source
            add_raw_series(chart, source_ws, x_col, y_col, last_row)
        add_max_min_series(chart, results_ws, n_cycles)
        chart.legend.position = "b"
        chart.legend.overlay = False
        return chart

    combined_charts = []
    maxmin_charts = []

    for gi, group in enumerate(groups):
        time_col, value_cols, n_rows = layout[gi]
        step = max(1, (n_rows // CHART_MAX_POINTS) + 1) if n_rows > CHART_MAX_POINTS else 1
        last_row = n_rows + 1

        if step == 1:
            source_ws = raw_ws
            source_time_col = time_col
            source_value_cols = value_cols
            source_last_row = last_row
        else:
            # Reference() cannot stride rows, so downsampled chart series
            # are built from a hidden helper sheet with every Nth row of
            # this group only.
            if helper_ws is None:
                helper_ws = wb.create_sheet("_chart_data")
                helper_ws.sheet_state = "hidden"
            base_col = helper_ws.max_column + 1 if helper_ws.max_column > 1 else 1
            names = [name for name, _v, _c in group.signals]
            for i, h in enumerate(["Time"] + names):
                helper_ws.cell(row=1, column=base_col + i, value=h)
            out_row = 2
            for r in range(1, n_rows, step):
                helper_ws.cell(row=out_row, column=base_col, value=raw_ws.cell(row=r + 1, column=time_col).value)
                for i, vcol in enumerate(value_cols):
                    helper_ws.cell(
                        row=out_row, column=base_col + 1 + i, value=raw_ws.cell(row=r + 1, column=vcol).value
                    )
                out_row += 1
            source_ws = helper_ws
            source_time_col = base_col
            source_value_cols = [base_col + 1 + i for i in range(len(value_cols))]
            source_last_row = out_row - 1

        for i, (name, _values, _cycles) in enumerate(group.signals):
            results_ws = wb[f"{name} Results"]
            n_cycles = max(0, results_ws.max_row - 2)
            raw_source = (source_ws, source_time_col, source_value_cols[i], source_last_row)
            combined_charts.append(
                make_chart(
                    f"{name} vs Time (with per-cycle Max & Min)",
                    name,
                    raw_source=raw_source,
                    results_ws=results_ws,
                    n_cycles=n_cycles,
                )
            )
            maxmin_charts.append(
                make_chart(
                    f"{name} Max & Min vs Time",
                    name,
                    raw_source=None,
                    results_ws=results_ws,
                    n_cycles=n_cycles,
                )
            )

    row = 1
    for chart in combined_charts + maxmin_charts:
        ws.add_chart(chart, f"A{row}")
        row += 25

    return ws


def write_workbook(output_path: str | Path, groups: Sequence[SignalGroup]) -> None:
    """Write Raw Data, one Results sheet per signal, and Charts.

    Each group in `groups` shares one Time column; groups may have
    different row counts (independent sampling devices). Two charts are
    produced per signal (raw-with-overlay, and Max/Min-only) — e.g. 4
    charts total for a Stress+Strain group, 2 more for an Extension group.
    """
    wb = Workbook()
    wb.remove(wb.active)  # drop default empty sheet

    _raw_ws, layout = _write_raw_data_sheet(wb, groups)
    for group in groups:
        for name, _values, cycles in group.signals:
            _write_results_sheet(wb, f"{name} Results", cycles)
    _add_charts_sheet(wb, groups, layout)

    wb.save(str(output_path))

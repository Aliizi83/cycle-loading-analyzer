"""Command-line entry point.

Supports two modes:
- Flag-based (scriptable): --input, --output, --stress-threshold, etc.
- Interactive: run with no arguments (or --interactive) and answer prompts.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .detector import (
    detect_extrema,
    extrema_to_cycles,
    merge_secondary_reversals,
    suggest_threshold,
    trailing_incomplete_extremum,
)
from .cross_reference import build_cross_reference_tables
from .cycle_labeling import cycle_labels, peak_to_peak_boundaries, zero_crossing_boundaries
from .excel_writer import SignalGroup, write_workbook
from .io_utils import read_combined_data


def _parse_yes_no(value: str) -> bool:
    v = value.strip().lower()
    if v in ("yes", "y", "true", "1"):
        return True
    if v in ("no", "n", "false", "0"):
        return False
    raise argparse.ArgumentTypeError(f"expected yes/no, got {value!r}")


def _parse_threshold(value: str) -> float | None:
    if value.strip().lower() == "auto":
        return None
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number or 'auto', got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyclic-loading-analyzer",
        description=(
            "Extract Max/Min points of every loading cycle for Stress and "
            "Strain (and, if present, a second signal like Extension) from "
            "cyclic loading test data, and write a formatted Excel "
            "workbook with results and charts. Run with no arguments to "
            "be prompted interactively instead."
        ),
    )
    parser.add_argument("--input", help="path to input file (csv or xlsx)")
    parser.add_argument("--output", help="path to output xlsx file")
    parser.add_argument(
        "--stress-threshold",
        type=_parse_threshold,
        help="reversal threshold for the Stress signal, or 'auto' / omit to auto-compute",
    )
    parser.add_argument(
        "--strain-threshold",
        type=_parse_threshold,
        help="reversal threshold for the Strain signal, or 'auto' / omit to auto-compute",
    )
    parser.add_argument(
        "--extension-threshold",
        type=_parse_threshold,
        help="reversal threshold for the Extension signal (columns 4-5, if present), "
        "or 'auto' / omit to auto-compute",
    )
    parser.add_argument(
        "--show-last-cycle",
        type=_parse_yes_no,
        default=None,
        help="yes/no, default no (the last cycle may be incomplete)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="force interactive prompts even if flags are also given",
    )
    return parser


def _prompt_path(message: str, *, must_exist: bool) -> Path:
    while True:
        raw = input(message).strip().strip('"').strip("'")
        if not raw:
            print("  Please enter a path.")
            continue
        path = Path(raw).expanduser()
        if must_exist and not path.exists():
            print(f"  File not found: {path}")
            continue
        if must_exist and path.suffix.lower() not in (".csv", ".xlsx", ".xlsm", ".xls"):
            print(f"  Unsupported file type: {path.suffix!r} (expected .csv or .xlsx)")
            continue
        return path


def _prompt_threshold(message: str) -> float | None:
    while True:
        raw = input(f"{message} [number, or leave blank to auto-compute]: ").strip()
        if not raw or raw.lower() == "auto":
            return None
        try:
            return float(raw)
        except ValueError:
            print(f"  Not a number: {raw!r}")


def _prompt_yes_no(message: str, default: bool) -> bool:
    default_label = "yes" if default else "no"
    while True:
        raw = input(f"{message} [yes/no, default {default_label}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("yes", "y"):
            return True
        if raw in ("no", "n"):
            return False
        print("  Please answer yes or no.")


def prompt_for_args() -> argparse.Namespace:
    print("Cyclic loading analyzer - interactive mode")
    print("(press Ctrl+C to cancel)\n")

    input_path = _prompt_path("Input file (csv or xlsx): ", must_exist=True)

    default_output = input_path.with_name(input_path.stem + "_results.xlsx")
    raw_output = input(f"Output xlsx file [default: {default_output}]: ").strip().strip('"').strip("'")
    output_path = Path(raw_output).expanduser() if raw_output else default_output

    stress_threshold = _prompt_threshold("Stress reversal threshold")
    strain_threshold = _prompt_threshold("Strain reversal threshold")
    extension_threshold = _prompt_threshold("Extension reversal threshold (ignored if the file has no 4th/5th column)")
    show_last_cycle = _prompt_yes_no("Include the last (possibly incomplete) cycle?", default=False)

    return argparse.Namespace(
        input=str(input_path),
        output=str(output_path),
        stress_threshold=stress_threshold,
        strain_threshold=strain_threshold,
        extension_threshold=extension_threshold,
        show_last_cycle=show_last_cycle,
        interactive=True,
    )


def _extrema_for_cycles(
    time,
    value,
    extrema: list,
    show_last_cycle: bool,
) -> list:
    """Extend `extrema` with a best-effort trailing extremum when the
    recording ends mid-swing and `show_last_cycle` is True, so that final
    half-cycle isn't silently dropped for lack of a confirmed partner. See
    `detector.trailing_incomplete_extremum`. A no-op whenever `extrema`
    already ends in a complete Max/Min pair, or `show_last_cycle` is False.
    """
    if show_last_cycle and len(extrema) % 2 == 1:
        trailing = trailing_incomplete_extremum(time, value, extrema)
        if trailing is not None:
            return extrema + [trailing]
    return extrema


def cycles_for_signal(
    time, values, threshold: float | None, show_last_cycle: bool
) -> tuple[list, float, int]:
    """Run the full detection pipeline for one signal.

    Auto-computes the threshold if `threshold` is None, detects extrema,
    removes brief secondary reversals nested inside a real half-cycle (see
    `detector.merge_secondary_reversals` — this and everything below only
    affects which points count as cycle peaks/valleys, never the raw
    signal), best-effort completes a final half-cycle that never confirmed
    when `show_last_cycle` is True, and pairs everything into cycles.

    Returns (cycles, threshold_used, reversals_merged_count).
    """
    if threshold is None:
        threshold = suggest_threshold(time, values)

    extrema = detect_extrema(time, values, threshold)
    merged = merge_secondary_reversals(extrema)
    reversals_merged = len(extrema) - len(merged)

    extrema = _extrema_for_cycles(time, values, merged, show_last_cycle)
    cycles = extrema_to_cycles(extrema, show_last_cycle)

    return cycles, threshold, reversals_merged


@dataclass
class SignalOutcome:
    name: str
    n_cycles: int
    threshold: float
    reversals_merged: int


@dataclass
class ProcessResult:
    raw_rows: int
    outcomes: list[SignalOutcome]
    extension_rows: int | None = None

    def outcome(self, name: str) -> SignalOutcome:
        return next(o for o in self.outcomes if o.name == name)


def process(
    input_path: Path,
    output_path: Path,
    stress_threshold: float | None,
    strain_threshold: float | None,
    extension_threshold: float | None,
    show_last_cycle: bool,
    cycle_label_fn=None,
) -> ProcessResult:
    """Run detection + write one workbook for a raw_data file.

    Columns 1-3 are always Time/Stress/Strain. If columns 4-5 are also
    present (a second, independently-sampled Time/<signal> pair — e.g.
    Time/Extension from an LVDT), that signal is detected and charted too,
    in the SAME output workbook (see `io_utils.read_combined_data`).

    Pass `None` for any threshold to auto-compute it as a fraction of that
    signal's own peak-to-peak range (see `detector.suggest_threshold`).

    `cycle_label_fn`, if given, relabels every "Cycle" column produced —
    the cross-reference sheets (see
    `cross_reference.build_cross_reference_tables`) and the per-row Cycle
    columns in "Raw Data" (see `cycle_labeling.cycle_labels`) — e.g.
    `cross_reference.paired_cycle_label` to fold every two consecutive
    cycles into "1_1"/"1_2"/"2_1"/"2_2"/... Has no effect on the Stress/
    Strain Cycle column's numbering scope, nor on files without a
    4th/5th-column signal for the Extension one.
    """
    main_df, ext_df, ext_name = read_combined_data(input_path)

    time = main_df["Time"].to_numpy()
    stress = main_df["Stress"].to_numpy()
    strain = main_df["Strain"].to_numpy()

    stress_cycles, stress_threshold, stress_merged = cycles_for_signal(
        time, stress, stress_threshold, show_last_cycle
    )
    strain_cycles, strain_threshold, strain_merged = cycles_for_signal(
        time, strain, strain_threshold, show_last_cycle
    )

    main_boundaries = zero_crossing_boundaries(time, stress, stress_cycles)
    main_row_labels = cycle_labels(time, main_boundaries, cycle_label_fn)

    groups = [
        SignalGroup(
            time=time,
            signals=[("Stress", stress, stress_cycles), ("Strain", strain, strain_cycles)],
            cycle_labels=main_row_labels,
        )
    ]
    outcomes = [
        SignalOutcome("Stress", len(stress_cycles), stress_threshold, stress_merged),
        SignalOutcome("Strain", len(strain_cycles), strain_threshold, strain_merged),
    ]
    extension_rows = None
    cross_reference_tables = None

    if ext_df is not None:
        ext_time = ext_df["Time"].to_numpy()
        ext_values = ext_df[ext_name].to_numpy()
        ext_cycles, ext_threshold, ext_merged = cycles_for_signal(
            ext_time, ext_values, extension_threshold, show_last_cycle
        )
        ext_boundaries = peak_to_peak_boundaries(ext_cycles)
        ext_row_labels = cycle_labels(ext_time, ext_boundaries, cycle_label_fn)
        groups.append(
            SignalGroup(
                time=ext_time,
                signals=[(ext_name, ext_values, ext_cycles)],
                cycle_labels=ext_row_labels,
            )
        )
        outcomes.append(SignalOutcome(ext_name, len(ext_cycles), ext_threshold, ext_merged))
        extension_rows = len(ext_df)

        cross_reference_tables = build_cross_reference_tables(
            time,
            stress,
            strain,
            stress_cycles,
            strain_cycles,
            ext_time,
            ext_values,
            ext_name,
            ext_cycles,
            cycle_label_fn,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(output_path, groups, cross_reference_tables)

    return ProcessResult(raw_rows=len(main_df), outcomes=outcomes, extension_rows=extension_rows)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Thresholds default to auto-computed (None) and don't require interactive
    # fallback; only input/output have no sensible default.
    required_missing = args.input is None or args.output is None

    if args.interactive or required_missing:
        try:
            args = prompt_for_args()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 1

    if args.show_last_cycle is None:
        args.show_last_cycle = False
    if not hasattr(args, "extension_threshold"):
        args.extension_threshold = None

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input file not found: {input_path}")

    result = process(
        input_path,
        Path(args.output),
        args.stress_threshold,
        args.strain_threshold,
        args.extension_threshold,
        args.show_last_cycle,
    )

    parts = [
        f"{o.n_cycles} {o.name.lower()} cycles [threshold {o.threshold:g}]" for o in result.outcomes
    ]
    print(f"Wrote {args.output} ({', '.join(parts)}, {result.raw_rows} raw rows)")

    merged_parts = [f"{o.reversals_merged} {o.name.lower()}" for o in result.outcomes if o.reversals_merged]
    if merged_parts:
        print(f"  Removed brief secondary reversals: {', '.join(merged_parts)} (not real cycle peaks/valleys).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

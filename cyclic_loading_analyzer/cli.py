"""Command-line entry point.

Supports two modes:
- Flag-based (scriptable): --input, --output, --stress-threshold, etc.
- Interactive: run with no arguments (or --interactive) and answer prompts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .detector import detect_extrema, extrema_to_cycles, suggest_threshold
from .excel_writer import write_workbook
from .io_utils import read_raw_data


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
            "Strain signals from cyclic loading test data, and write a "
            "formatted Excel workbook with results and charts. Run with no "
            "arguments to be prompted interactively instead."
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
    show_last_cycle = _prompt_yes_no("Include the last (possibly incomplete) cycle?", default=False)

    return argparse.Namespace(
        input=str(input_path),
        output=str(output_path),
        stress_threshold=stress_threshold,
        strain_threshold=strain_threshold,
        show_last_cycle=show_last_cycle,
        interactive=True,
    )


def process(
    input_path: Path,
    output_path: Path,
    stress_threshold: float | None,
    strain_threshold: float | None,
    show_last_cycle: bool,
) -> tuple[int, int, int, float, float, int, int]:
    """Run detection + write the workbook.

    Pass `None` for either threshold to auto-compute it as a fraction of
    that signal's own peak-to-peak range (see `detector.suggest_threshold`).

    Returns (stress_cycles, strain_cycles, raw_rows, stress_threshold_used,
    strain_threshold_used).
    """
    raw_df = read_raw_data(input_path)

    time = raw_df["Time"].to_numpy()
    stress = raw_df["Stress"].to_numpy()
    strain = raw_df["Strain"].to_numpy()

    if stress_threshold is None:
        stress_threshold = suggest_threshold(stress)
    if strain_threshold is None:
        strain_threshold = suggest_threshold(strain)

    stress_extrema = detect_extrema(time, stress, stress_threshold)
    strain_extrema = detect_extrema(time, strain, strain_threshold)

    stress_cycles = extrema_to_cycles(stress_extrema, show_last_cycle)
    strain_cycles = extrema_to_cycles(strain_extrema, show_last_cycle)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(output_path, raw_df, stress_cycles, strain_cycles)

    return (
        len(stress_cycles),
        len(strain_cycles),
        len(raw_df),
        stress_threshold,
        strain_threshold,
    )


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

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input file not found: {input_path}")

    stress_cycles, strain_cycles, raw_rows, stress_threshold, strain_threshold = process(
        input_path,
        Path(args.output),
        args.stress_threshold,
        args.strain_threshold,
        args.show_last_cycle,
    )

    print(
        f"Wrote {args.output} "
        f"({stress_cycles} stress cycles [threshold {stress_threshold:g}], "
        f"{strain_cycles} strain cycles [threshold {strain_threshold:g}], "
        f"{raw_rows} raw rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

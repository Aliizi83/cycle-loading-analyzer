"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .detector import detect_extrema, extrema_to_cycles
from .excel_writer import write_workbook
from .io_utils import read_raw_data


def _parse_yes_no(value: str) -> bool:
    v = value.strip().lower()
    if v in ("yes", "y", "true", "1"):
        return True
    if v in ("no", "n", "false", "0"):
        return False
    raise argparse.ArgumentTypeError(f"expected yes/no, got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyclic-loading-analyzer",
        description=(
            "Extract Max/Min points of every loading cycle for Stress and "
            "Strain signals from cyclic loading test data, and write a "
            "formatted Excel workbook with results and charts."
        ),
    )
    parser.add_argument("--input", required=True, help="path to input file (csv or xlsx)")
    parser.add_argument("--output", required=True, help="path to output xlsx file")
    parser.add_argument(
        "--stress-threshold",
        required=True,
        type=float,
        help="reversal threshold for the Stress signal",
    )
    parser.add_argument(
        "--strain-threshold",
        required=True,
        type=float,
        help="reversal threshold for the Strain signal",
    )
    parser.add_argument(
        "--show-last-cycle",
        type=_parse_yes_no,
        default=False,
        help="yes/no, default no (the last cycle may be incomplete)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input file not found: {input_path}")

    raw_df = read_raw_data(input_path)

    time = raw_df["Time"].to_numpy()
    stress = raw_df["Stress"].to_numpy()
    strain = raw_df["Strain"].to_numpy()

    stress_extrema = detect_extrema(time, stress, args.stress_threshold)
    strain_extrema = detect_extrema(time, strain, args.strain_threshold)

    stress_cycles = extrema_to_cycles(stress_extrema, args.show_last_cycle)
    strain_cycles = extrema_to_cycles(strain_extrema, args.show_last_cycle)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(output_path, raw_df, stress_cycles, strain_cycles)

    print(
        f"Wrote {output_path} "
        f"({len(stress_cycles)} stress cycles, {len(strain_cycles)} strain cycles, "
        f"{len(raw_df)} raw rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CLI entry point for generating loan document scenarios.

Usage:
    uv run python -m generator.generate --count 10 --output generated_docs/

Generates N complete loan scenarios, each producing 5 linked PDF documents.
"""

import argparse
import sys
import time
from pathlib import Path

from generator.scenario import LoanScenario
from generator.templates import DOCUMENT_TYPES


def generate_scenario_documents(scenario: LoanScenario, output_dir: Path) -> list[Path]:
    """Generate all 5 document types for a single loan scenario.

    Returns the list of file paths created.
    """
    loan_dir = output_dir / scenario.loan_id
    loan_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for doc_type, config in DOCUMENT_TYPES.items():
        pdf_bytes = config["generator"](scenario)
        file_path = loan_dir / f"{doc_type}.pdf"
        file_path.write_bytes(pdf_bytes)
        paths.append(file_path)

    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic loan document scenarios for DocumentStream"
    )
    parser.add_argument(
        "--count", "-n", type=int, default=10, help="Number of loan scenarios to generate"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="generated_docs",
        help="Output directory for generated documents",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.count} loan scenarios ({args.count * 5} documents)...")
    start = time.time()

    for i in range(args.count):
        scenario = LoanScenario.generate()
        paths = generate_scenario_documents(scenario, output_dir)
        print(f"  [{i + 1}/{args.count}] {scenario.loan_id}: {len(paths)} documents")

    elapsed = time.time() - start
    total_docs = args.count * len(DOCUMENT_TYPES)
    rate = total_docs / elapsed
    print(f"Done. Generated {total_docs} documents in {elapsed:.1f}s ({rate:.0f} docs/sec)")


if __name__ == "__main__":
    sys.exit(main() or 0)

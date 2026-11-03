"""Single-question CLI for the FlowSense analytics agent."""

import argparse
import json
import os
from pathlib import Path

from flowsense.agent import AnalyticsTools, ask, render_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--database", type=Path, default=Path("data/flowsense.sqlite"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--position-lag", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Optional JSON answer and tool trace")
    parser.add_argument("--check-tools", action="store_true", help="Offline coverage and latest metrics check; no LLM")
    args = parser.parse_args()
    try:
        if not args.check_tools:
            if not args.question or not args.model:
                parser.error("Provide a question and --model (or OPENAI_MODEL)")
            if not os.environ.get("OPENAI_API_KEY"):
                parser.error("Set OPENAI_API_KEY in the terminal; do not put it in source files")
        tools = AnalyticsTools(args.database, args.window, args.position_lag)
        if args.check_tools:
            print(json.dumps(tools.execute("describe_dataset", {}), indent=2))
            print(json.dumps(tools.execute("get_metrics", {
                "region": "US", "asset_class": "equities", "start_date": None,
                "end_date": None, "limit": 1}), indent=2))
            return
        result = ask(args.question, tools, args.model)
        print(render_answer(result))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"FlowSense: {error}\n")


if __name__ == "__main__":
    main()

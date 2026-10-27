#!/usr/bin/env python3
"""Run the example requests and write what they answered.

The outputs in ``output_examples/`` are produced by real runs. Nothing
in the application ever reads them: they are there so a reader can see
what the API returns without running it.

    python3 scripts/generate_examples.py

Every output records the run id and the trace it wrote, so the run can
be inspected afterwards.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app import run_payload  # noqa: E402

INPUTS = ROOT / "input_examples"
OUTPUTS = ROOT / "output_examples"


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    written = []

    for path in sorted(INPUTS.glob("*.json")):
        request = json.loads(path.read_text(encoding="utf-8"))
        print(f"Running {path.name}...")
        # The log goes to stderr; stdout carries the answers.
        payload = run_payload(request, echo="stderr")

        out = OUTPUTS / path.name.replace(".json", "_output.json")
        out.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        written.append(out.name)
        print(
            f"  -> {out.name}: status={payload['status']} "
            f"findings={len(payload['findings'])} "
            f"run={payload['run_id']}"
        )

    print(f"Wrote {len(written)} outputs to {OUTPUTS}")


if __name__ == "__main__":
    main()

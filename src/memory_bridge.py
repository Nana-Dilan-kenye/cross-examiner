"""Python bridge to the persistent H-MEM store."""
import json
import os
import subprocess
from pathlib import Path

AGENT_DIR = Path(
    os.environ.get("HMEM_AGENT_DIR", str(Path.home() / "hackathon" / "my-agent"))
).expanduser()


def _run(*args):
    result = subprocess.run(
        ["npx", "tsx", "cross_examiner_memory.ts", *args],
        cwd=AGENT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def remember(content, source, refs=None, tags=None, confidence=0.7):
    return _run("remember", json.dumps({
        "content": content,
        "source": source,
        "refs": refs or [],
        "tags": tags or [],
        "confidence": confidence,
    }))


def query(question):
    return _run("query", question)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cross-Examiner H-MEM bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    save = sub.add_parser("remember")
    save.add_argument("content")
    save.add_argument("--source", required=True)
    save.add_argument("--ref", action="append", default=[])
    ask = sub.add_parser("query")
    ask.add_argument("question")
    args = parser.parse_args()

    if args.command == "remember":
        print(json.dumps(remember(args.content, args.source, args.ref), indent=2))
    else:
        print(json.dumps(query(args.question), indent=2))

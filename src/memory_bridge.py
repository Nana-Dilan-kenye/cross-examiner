"""The Meterless H-MEM engine bridge for Cross-Examiner.

The engine is the persistent memory: the first investigation stores what
it found, and a later one retrieves it and changes its plan because of
it.

The engine itself is the Meterless H-MEM reference, vendored under
``engine/vendor/hmem`` in this repository (Apache-2.0, zero runtime
dependencies). The bridge is ``engine/cross_examiner_memory.ts``.

It needs Node 18 or newer and the TypeScript runner:

    cd engine && npm install

If the bridge cannot be reached, the application carries on without the
memory and says so: the health report and every run record what
happened.
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The engine in this repository, and the starter it came from.
ENGINE_DIR = ROOT / "engine"
STARTER_DIR = Path.home() / "hackathon" / "my-agent"

# tsx needs a modern Node runtime.
MIN_NODE_MAJOR = 18


class MemoryBridgeUnavailable(RuntimeError):
    """The H-MEM bridge could not be reached."""


def engine_dir():
    """Where the engine lives."""
    override = os.environ.get("HMEM_ENGINE_DIR")
    if override:
        return Path(override).expanduser()
    if (ENGINE_DIR / "cross_examiner_memory.ts").is_file():
        return ENGINE_DIR
    return STARTER_DIR


def _node_hint():
    """Explain a Node version problem, if that is what happened."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = (result.stdout or "").strip()
        major = int(version.lstrip("v").split(".")[0])
    except Exception:
        return None
    if major < MIN_NODE_MAJOR:
        return (
            f"node {version} is too old for the H-MEM bridge "
            f"(tsx needs Node {MIN_NODE_MAJOR}+); the bridge was not run."
        )
    return None


def _diagnose(stderr):
    """Short, readable explanation of a bridge failure.

    The bridge prints minified JavaScript on syntax errors, so lines are
    truncated and only the tail is kept.
    """
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    if not lines:
        return "The H-MEM bridge exited with an error."

    errors = [line for line in lines if "error" in line.casefold()]
    tail = (errors or lines)[-3:]
    message = " ".join(line[:200] for line in tail).strip()

    hint = _node_hint()
    if hint:
        return f"{hint} {message}"[:400]
    return message[:400]


def _tsx_command():
    """How to run the TypeScript bridge.

    The engine's own runner is preferred, because it is the one the
    repository installed; ``npx`` is the fallback for a checkout that
    has not run the setup step.
    """
    local = engine_dir() / "node_modules" / ".bin" / "tsx"
    if local.is_file():
        return [str(local)]
    return ["npx", "tsx"]


def _run(*args):
    try:
        result = subprocess.run(
            _tsx_command() + ["cross_examiner_memory.ts", *args],
            cwd=str(engine_dir()),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise MemoryBridgeUnavailable(_diagnose(exc.stderr)) from None
    except OSError as exc:
        raise MemoryBridgeUnavailable(
            f"Cannot start the H-MEM bridge ({exc})."
        ) from None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise MemoryBridgeUnavailable(
            "The H-MEM bridge returned output that was not JSON."
        )


def remember(content, source, refs=None, tags=None, confidence=0.7):
    """Store a memory. Returns a result dict; on failure it carries an error."""
    try:
        return _run("remember", json.dumps({
            "content": content,
            "source": source,
            "refs": refs or [],
            "tags": tags or [],
            "confidence": confidence,
        }))
    except MemoryBridgeUnavailable as exc:
        return {"ok": False, "id": None, "error": str(exc)}


def query(question, top_n=None):
    """Retrieve memories. Returns context plus an availability flag.

    The store ranks every memory it holds, so the candidate list is wide
    and the caller filters by topic.
    """
    if top_n:
        os.environ["HMEM_TOP_N"] = str(int(top_n))
    try:
        result = _run("query", question)
    except MemoryBridgeUnavailable as exc:
        return {
            "context": "",
            "memories": [],
            "trace": None,
            "available": False,
            "error": str(exc),
        }

    result.setdefault("memories", [])
    result["available"] = True
    result["error"] = None
    return result


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

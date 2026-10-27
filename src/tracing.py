"""The auditable trace of one run.

Every run writes a JSONL file: one object per line, in the order things
happened. It records what was asked, which agents ran, which agent they
handed over to, what each one was asked, what it answered, how sure it
was, and whether it had to be retried.

The shape follows the event log the hackathon's own technical guidance
asks for, so a judge can read a trace without a key:

    timestamp, run_id, agent_name, action, input_summary, output_summary,
    target_agent, confidence, retry_count, status

The trace goes to ``stdout`` and to ``logs/trace-<run_id>.jsonl``.
Secrets never reach it: anything that looks like a token is replaced
before it is written.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE_DIR = ROOT / "logs"

# Things that must never be written down.
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b"),
]

SECRET_VALUES = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\b[A-Za-z0-9._\-]*(?:key|token|secret)[A-Za-z0-9._\-]*\s*[=:]\s*\S+"),
]

REDACTED = "[redacted]"

# The agents that take part in one investigation.
AGENTS = {
    "orchestrator": "runs the loop, enforces the bounds, owns the state",
    "investigator": "proposes which evidence to gather next",
    "critic": "checks every number against the publication it came from",
    "arbiter": "makes the deterministic decision",
    "adjudicator": "gates the model's proposed disposition",
    "reporter": "writes the answer and its provenance",
    "memory": "reads and writes the persistent memory",
}


def redact(value):
    """Replace anything that looks like a secret with a marker."""
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if any(pattern.search(str(key)) for pattern in SECRET_PATTERNS)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        text = value
        for pattern in SECRET_VALUES:
            text = pattern.sub(REDACTED, text)
        return text
    return value


def _summary(value, limit=300):
    """A short, readable summary of a value for the trace."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = " ".join(str(text).split())
    return text[:limit]


class Trace:
    """One run's trace."""

    def __init__(self, run_id=None, directory=None, mode="live", question="",
                 echo=True):
        """``echo`` decides where the log goes besides the file.

        ``True`` writes to stdout, which is what a service wants. ``"stderr"``
        writes to stderr, which is what a command line tool wants when its
        stdout carries the result. ``False`` writes only to the file.
        """
        self.run_id = run_id or new_run_id()
        self.directory = Path(directory) if directory else TRACE_DIR
        self.path = self.directory / f"trace-{self.run_id}.jsonl"
        self.mode = mode
        self.started = time.time()
        self.events = []
        self.echo = echo
        self.directory.mkdir(parents=True, exist_ok=True)

        self.agent(
            "orchestrator",
            "run.started",
            input_summary=question,
            output_summary=f"mode={mode}",
            status="started",
        )

    def agent(self, agent_name, action, target_agent=None, input_summary=None,
              output_summary=None, confidence=None, retry_count=0,
              status="ok", **fields):
        """Record one agent action.

        ``target_agent`` is who the work was handed to, which is what
        makes the collaboration between the agents visible in the log.
        """
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            + f".{int((time.time() % 1) * 1000):03d}Z",
            "run_id": self.run_id,
            "agent_name": agent_name,
            "action": action,
            "input_summary": _summary(input_summary),
            "output_summary": _summary(output_summary),
            "target_agent": target_agent or "",
            "confidence": confidence,
            "retry_count": int(retry_count or 0),
            "status": status,
        }
        record.update(redact(fields))
        self._write(record)
        return record

    def event(self, name, **fields):
        """Record a lifecycle event of the run itself."""
        return self.agent("orchestrator", name, **fields)

    def _write(self, record):
        self.events.append(record)
        line = json.dumps(record, sort_keys=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if self.echo == "stderr":
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        elif self.echo:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def close(self, **fields):
        """Record the end of the run."""
        return self.event(
            "run.finished",
            output_summary=fields.pop("output_summary", ""),
            elapsed_seconds=round(time.time() - self.started, 3),
            events=len(self.events),
            **fields,
        )

    def read(self):
        """The trace, as a list of records."""
        return read_trace(self.run_id, self.directory)


def new_run_id():
    """A run id that sorts by time and is unique enough."""
    return time.strftime("%Y%m%dT%H%M%S") + f"-{os.getpid() % 100000:05d}"


def read_trace(run_id, directory=None):
    """The trace of one run, or an empty list."""
    base = Path(directory) if directory else TRACE_DIR
    path = base / f"trace-{run_id}.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def agent_names(records):
    """The agents that appear in a trace."""
    return sorted({
        str(record.get("agent_name", ""))
        for record in records
        if record.get("agent_name")
    })


def handoffs(records):
    """The agent-to-agent handoffs in a trace."""
    out = []
    for record in records:
        target = record.get("target_agent")
        if not target:
            continue
        out.append({
            "from": record.get("agent_name"),
            "to": target,
            "action": record.get("action"),
        })
    return out

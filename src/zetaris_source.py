"""Read Cross-Examiner evidence from Zetaris."""
import importlib.util
import json
import os
from pathlib import Path

DEFAULT_HELPER = (
    Path.home() / "hackathon" / "zetaris-getting-started" / "scripts"
)


def load_records():
    helper_dir = Path(
        os.environ.get("ZETARIS_HELPER_DIR", str(DEFAULT_HELPER))
    ).expanduser()
    client_file = helper_dir / "zetaris_sql.py"

    if not client_file.is_file():
        raise FileNotFoundError(f"Zetaris client not found: {client_file}")

    spec = importlib.util.spec_from_file_location(
        "cross_examiner_zetaris_sql", client_file
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Zetaris client: {client_file}")

    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    client.load_env()
    channel = client.open_channel("rest")

    try:
        result = channel.run(
            "SELECT * FROM CROSS_EXAMINER_EVIDENCE.evidence_raw",
            limit=1000,
        )

        records = []
        for row in result.rows:
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)

            if isinstance(payload, dict):
                payload = [payload]

            for item in payload:
                records.append({
                    "country": item["country"],
                    "antigen": item["antigen"],
                    "year": str(item["year"]),
                    "measure": item["measure"],
                    "value_percent": str(item["value_percent"]),
                    "source": item.get("source", ""),
                    "source_url": item.get("source_url", ""),
                    "notes": item.get("notes", ""),
                })

        return records
    finally:
        channel.close()

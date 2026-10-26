"""Read Cross-Examiner evidence from Zetaris."""
import importlib.util
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
            "SELECT country, antigen, year, measure, value_percent, "
            "source_name, source_url, notes "
            "FROM lightning.metastore.cross_examiner.cross_examiner_evidence.evidence",
            limit=1000,
        )
        columns = [
            "country", "antigen", "year", "measure", "value_percent",
            "source", "source_url", "notes",
        ]
        return [dict(zip(columns, row)) for row in result.rows]
    finally:
        channel.close()

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from openpyxl import load_workbook
import csv
import json

ROOT = Path(__file__).resolve().parent.parent
CSV_DATA = ROOT / "data" / "cameroon_mcv1_evidence.csv"
XLSX_DATA = ROOT / "data" / "wuenic2025rev_web-update.xlsx"
WUENIC_URL = "https://data.unicef.org/resources/dataset/immunization/"


def load_csv_evidence():
    with CSV_DATA.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_wuenic():
    wb = load_workbook(XLSX_DATA, read_only=True, data_only=True)
    try:
        ws = wb["country"]
        rows = ws.iter_rows(values_only=True)
        next(rows)  # Header

        records = []
        for row in rows:
            if (
                row[0] == "CMR"
                and row[2] == "mcv1"
                and row[4] == "si"
                and row[3] in (2020, 2023)
                and row[5] is not None
            ):
                records.append({
                    "country": row[1],
                    "antigen": "MCV1",
                    "year": str(row[3]),
                    "measure": "WUENIC estimate",
                    "value_percent": str(row[5]),
                    "source": str(row[6]),
                    "source_url": WUENIC_URL,
                    "notes": f"Workbook target group: {row[4]}",
                })
        return records
    finally:
        wb.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path).path

        if route == "/evidence":
            records = load_csv_evidence()
        elif route == "/wuenic":
            records = load_wuenic()
        else:
            self.send_error(404)
            return

        body = json.dumps({"evidence": records}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))


if __name__ == "__main__":
    print("Cross-Examiner evidence API listening on port 8765")
    HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()

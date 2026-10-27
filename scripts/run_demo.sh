#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p reports

# The evidence API is what the two Zetaris REST tables read. It is only
# needed for the --source zetaris run.
if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8765/evidence; then
  echo "Starting the evidence API..."
  python3 -m src.evidence_api &
  sleep 3
fi

echo "Running the deterministic investigation through the unified layer..."
python3 -m src.analyzer \
  --source zetaris \
  --model off \
  --report reports/cameroon_mcv1_zetaris_demo.md \
  > reports/cameroon_mcv1_results.json

echo "Running it with the model, if one is configured..."
python3 -m src.analyzer \
  --source zetaris \
  --question "Cameroon MCV1 coverage discrepancy 2020" \
  --model auto \
  --report reports/cameroon_mcv1_iterative_report.md \
  > reports/cameroon_mcv1_iterative_results.json

echo "Demo completed."
echo "JSON results: reports/cameroon_mcv1_results.json"
echo "Markdown report: reports/cameroon_mcv1_zetaris_demo.md"
echo "Iterative report: reports/cameroon_mcv1_iterative_report.md"

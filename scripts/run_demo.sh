#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p reports

python3 -m src.analyzer \
  --source zetaris \
  --report reports/cameroon_mcv1_zetaris_demo.md \
  > reports/cameroon_mcv1_results.json

echo "Demo completed."
echo "JSON results: reports/cameroon_mcv1_results.json"
echo "Markdown report: reports/cameroon_mcv1_zetaris_demo.md"

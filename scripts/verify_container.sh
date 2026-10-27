#!/usr/bin/env bash
# Verify the container against the running Zetaris instance.
#
# The container is built to run without credentials, but it can also read
# the deployed semantic layer: the Zetaris client helper is mounted, the
# API key is passed as a runtime environment variable, and the REST URL
# points at the host.
#
#   bash scripts/verify_container.sh
#
# Exits non-zero when the container cannot reach the layer.

set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-cross-examiner:local}"
PORT="${PORT:-8124}"
CLIENT_DIR="${ZETARIS_CLIENT_DIR:-$HOME/hackathon/zetaris-getting-started/scripts}"

if [ ! -f "$CLIENT_DIR/zetaris_sql.py" ]; then
  echo "The Zetaris client helper is not at $CLIENT_DIR."
  echo "Set ZETARIS_CLIENT_DIR to the getting-started scripts folder."
  exit 2
fi

API_KEY="${ZETARIS_API_KEY:-}"
if [ -z "$API_KEY" ] && [ -f "$HOME/hackathon/zetaris-getting-started/.env.local" ]; then
  API_KEY="$(grep -m1 '^ZETARIS_API_KEY=' \
    "$HOME/hackathon/zetaris-getting-started/.env.local" | cut -d= -f2-)"
fi
if [ -z "$API_KEY" ]; then
  echo "No Zetaris API key. Set ZETARIS_API_KEY, or leave it unset to"
  echo "check the container in sample mode instead."
  exit 2
fi

echo "Building $IMAGE..."
docker build -t "$IMAGE" . >/dev/null

echo "Starting the container against the running instance..."
docker rm -f cross-examiner-live >/dev/null 2>&1 || true
docker run -d --name cross-examiner-live -p "${PORT}:8000" \
  -e SAMPLE_MODE=false \
  -e ZETARIS_API_KEY="$API_KEY" \
  -e ZETARIS_REST_URL=http://host.docker.internal:8888/api/v1.0 \
  -e ZETARIS_ORG_ID=1 \
  -e ZETARIS_HELPER_DIR=/app/zetaris-client \
  -v "$CLIENT_DIR:/app/zetaris-client:ro" \
  "$IMAGE" >/dev/null

sleep 8

fail=0

echo
echo "--- GET /health ---"
health="$(curl -s --max-time 120 "http://127.0.0.1:${PORT}/health")"
echo "$health" | python3 -c "
import json, sys
d = json.load(sys.stdin)
layer = d['components']['zetaris_usl']
print('mode:', d['mode'])
print('semantic layer:', layer.get('object'))
print('reachable:', layer.get('reachable'), '| rows:', layer.get('rows'))
print('source ids:', layer.get('source_ids'))
print('memory:', d['components']['memory'].get('available'), d['components']['memory'].get('error') or '')
sys.exit(0 if layer.get('reachable') else 1)
" || fail=1

echo
echo "--- POST /run ---"
curl -s --max-time 300 -X POST "http://127.0.0.1:${PORT}/run" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Which Cameroon MCV1 coverage figure should we plan against for 2020?","country":"Cameroon","antigen":"MCV1","year":"2020","source":"auto","model":"off","use_memory":false}' \
  2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('run:', d['run_id'], '| status:', d['status'], '| mode:', d['mode'])
layer = d['semantic_layer'][0]
print('read from:', layer.get('read_from'), '| origin:', layer.get('origin'))
finding = d['findings'][0]
print('finding:', finding['country'], finding['year'],
      '| review:', finding['review_status'],
      '| confidence:', finding['confidence'])
print('lineage:', [(o['measure'], o['origin']) for o in finding['lineage']])
print('recommendation:', (finding.get('recommendation') or {}).get('recommended_measure'),
      (finding.get('recommendation') or {}).get('recommended_value'))
sys.exit(0 if layer.get('origin') == 'zetaris_usl' else 1)
" || fail=1

docker rm -f cross-examiner-live >/dev/null 2>&1 || true

echo
if [ "$fail" -eq 0 ]; then
  echo "The container reads the deployed semantic layer."
else
  echo "FAILED: the container did not read the semantic layer."
fi
exit "$fail"

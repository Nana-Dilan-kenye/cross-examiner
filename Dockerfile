# Cross-Examiner - the HTTP API.
#
# The image is self-contained: the evidence, the registry, the generated
# data and the H-MEM engine are copied in, and nothing is installed at
# run time.
#
#   docker build -t cross-examiner .
#   docker run --rm -p 8000:8000 cross-examiner
#
# SAMPLE_MODE is on by default, so the container runs without
# credentials and without a network: it answers from the files in the
# image. Turn it off and point the container at a Zetaris instance to
# read the deployed semantic layer:
#
#   docker run --rm -p 8000:8000 -e SAMPLE_MODE=false \
#     -e ZETARIS_API_KEY="$ZETARIS_API_KEY" \
#     -e ZETARIS_REST_URL=http://host.docker.internal:8888/api/v1.0 \
#     -e ZETARIS_HELPER_DIR=/app/zetaris-client \
#     -v ~/hackathon/zetaris-getting-started/scripts:/app/zetaris-client:ro \
#     cross-examiner
#
# `scripts/verify_container.sh` runs exactly that and checks the answer.
#
FROM node:22-slim AS node

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SAMPLE_MODE=true \
    PORT=8000

WORKDIR /app

# Node, for the H-MEM engine bridge.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

# The dependencies are installed while the image is built, never while
# it runs.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY eval ./eval
COPY data ./data
COPY docs ./docs
COPY ui ./ui
COPY engine ./engine
COPY run.py README.md ./

# The engine's TypeScript runner. If the network is unavailable the build
# still succeeds: the application then runs without the memory and says
# so in its health report.
RUN cd engine \
    && (npm install --no-audit --no-fund \
        && npm run setup --if-present) \
    || echo "the memory engine could not be prepared; the app runs without it"

RUN mkdir -p logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200 else 1)"

CMD ["python3", "-m", "src.app"]

-- =============================================================================
-- Source:   The two tables the unified layer is built on today.
-- Purpose:  Reproduce the objects that already exist in the instance, so
--           the Zetaris side of the project can be rebuilt after
--           `docker compose down -v` or on a fresh install.
-- Format:   REST/JSON, served by the project's own evidence API.
-- Docs:     data/registry/README.md
--
-- CAVEAT:   Both endpoints point at the project's own HTTP service. That
--           makes them a *transport* for the project's own files, not a
--           second opinion on them: the Zetaris tables hold the same rows
--           the application already had. The scripts in this folder that
--           register a genuinely external source (02, 03, 04) are what
--           make the unified layer span more than one upstream.
--
-- Before running: the evidence API has to be running and reachable from
--   the Zetaris driver container:
--   curl -s http://127.0.0.1:8765/evidence | head -c 200
--   docker exec zetaris-driver-1 curl -s http://host.docker.internal:8765/evidence | head -c 200
--
-- Status: live-tested on the local instance (2026-10-26).
-- =============================================================================

-- Step 0: the logical databases. Both are REST sources over the evidence
-- API, so they are registered as Lightning REST tables.
CREATE LIGHTNING DATABASE CROSS_EXAMINER_EVIDENCE DESCRIBE BY "Cross-Examiner local evidence API";

CREATE LIGHTNING DATABASE WUENIC_WORKBOOK DESCRIBE BY "WHO UNICEF workbook evidence source";

-- Step 1: the published coverage figures.
CREATE LIGHTNING REST TABLE evidence_raw FROM CROSS_EXAMINER_EVIDENCE REQUEST(
    endpoint "http://host.docker.internal:8765/evidence",
    method "get",
    response_type "json",
    http_encoding "URLENCODED"
) HEADER (
) BODY ();

-- Step 2: the WUENIC workbook extract.
CREATE LIGHTNING REST TABLE wuenic_raw FROM WUENIC_WORKBOOK REQUEST(
    endpoint "http://host.docker.internal:8765/wuenic",
    method "get",
    response_type "json",
    http_encoding "URLENCODED"
) HEADER (
) BODY ();

-- Step 3: the container that holds the views.
CREATE SCHEMASTORE CONTAINER cross_examiner;

-- Step 4: one flat row per reported number, one view per source.
CREATE SCHEMASTORE VIEW evidence_table WITH CONTAINER cross_examiner AS
SELECT
    item.country,
    item.antigen,
    item.year,
    item.measure,
    CAST(item.value_percent AS DOUBLE) AS value_percent,
    item.source,
    item.source_url,
    item.notes
FROM cross_examiner_evidence.evidence_raw
LATERAL VIEW explode(evidence) AS item;

CREATE SCHEMASTORE VIEW wuenic_workbook_table WITH CONTAINER cross_examiner AS
SELECT
    item.country AS country,
    item.antigen AS antigen,
    item.year AS year,
    item.measure AS measure,
    CAST(item.value_percent AS DOUBLE) AS value_percent,
    item.source AS source,
    item.source_url AS source_url,
    item.notes AS notes
FROM wuenic_workbook.wuenic_raw
LATERAL VIEW explode(evidence) AS item;

-- Step 5: the unified view the application reads. The estimate is taken
-- from the workbook, which is where it comes from, and the other measures
-- from the published figures, so a series is never counted twice.
CREATE SCHEMASTORE VIEW unified_evidence_table WITH CONTAINER cross_examiner AS
SELECT country, antigen, year, measure, value_percent, source, source_url, notes
FROM cross_examiner.evidence_table
WHERE measure <> "WUENIC estimate"
UNION ALL
SELECT country, antigen, year, measure, value_percent, source, source_url, notes
FROM cross_examiner.wuenic_workbook_table;

-- Step 6: the semantic layer over the unified view.
COMPILE USL cross_examiner_evidence DDL
CREATE TABLE cross_examiner_evidence (
    country STRING,
    antigen STRING,
    year STRING,
    measure STRING,
    value_percent DOUBLE,
    source_name STRING,
    source_url STRING,
    notes STRING
);
DEPLOY NAMESPACE lightning.metastore;

ACTIVATE USL TABLE lightning.metastore.cross_examiner.cross_examiner_evidence AS
SELECT
    country,
    antigen,
    year,
    measure,
    value_percent,
    `source` AS source_name,
    source_url,
    notes
FROM cross_examiner.unified_evidence_table;

-- =============================================================================
-- Teardown.
-- =============================================================================
-- DROP VIEW cross_examiner.unified_evidence_table;
-- DROP VIEW cross_examiner.evidence_table;
-- DROP VIEW cross_examiner.wuenic_workbook_table;
-- REMOVE USL cross_examiner_evidence NAMESPACE lightning.metastore;
-- DROP LIGHTNING DATABASE CROSS_EXAMINER_EVIDENCE;
-- DROP LIGHTNING DATABASE WUENIC_WORKBOOK;

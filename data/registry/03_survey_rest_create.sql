-- =============================================================================
-- Source:   The compiled sheet of published household-survey figures.
-- License:  Figures transcribed from the DHS Program's published report;
--           the DHS Program is authorised for public use with citation.
-- Format:   REST/JSON, served by the project's own evidence API.
-- Docs:     data/survey_figures.csv
--           https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf
--
-- WHY THE REST ROUTE AND NOT THE FILESTORE
--   The filestore connector works on this instance, but it only accepts
--   s3a:// paths: every local path form is rejected with "Invalid file
--   path to access". The details and the evidence are in
--   data/registry/05_survey_filestore_create.sql. The platform's own
--   documented local-file route goes through the user interface, which
--   Lightning SQL cannot reach.
--
--   So the sheet is served by the project's evidence API and registered
--   as a REST table. The lineage does not change: the rows are the
--   transcribed DHS figures, with the DHS report as their own
--   publication and cameroon_household_survey as their origin.
--
-- Before running:
--   curl -s http://127.0.0.1:8765/survey_figures | head -c 300
--   docker exec zetaris-driver-1 curl -s http://host.docker.internal:8765/survey_figures | head -c 300
--
-- Status: live-tested on the local instance (2026-10-26).
-- =============================================================================

CREATE LIGHTNING REST TABLE survey_figures_raw FROM CROSS_EXAMINER_EVIDENCE REQUEST(
    endpoint "http://host.docker.internal:8765/survey_figures",
    method "get",
    response_type "json",
    http_encoding "URLENCODED"
) HEADER (
) BODY ();

-- The verification query: the transcribed DHS figure.
SELECT item.country, item.antigen, item.year, item.value_percent, item.source_url
FROM cross_examiner_evidence.survey_figures_raw
LATERAL VIEW explode(evidence) AS item;

-- =============================================================================
-- Teardown.
-- =============================================================================
-- DROP LIGHTNING DATABASE CROSS_EXAMINER_EVIDENCE;

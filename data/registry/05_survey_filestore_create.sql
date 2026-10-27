-- =============================================================================
-- Source:   The compiled sheet of published household-survey figures.
-- License:  Figures transcribed from the DHS Program's published report;
--           the DHS Program is authorised for public use with citation.
-- Format:   CSV file. The Zetaris filestore connector reads CSV, JSON,
--           Parquet, ORC, Delta, XML, Avro and a few document formats --
--           it does NOT read XLSX, so the sheet is CSV.
-- Docs:     data/survey_figures.csv
--           https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf
--
-- STATUS: BLOCKED ON THIS INSTANCE -- DO NOT RUN AS WRITTEN
--
--   The filestore connector itself works here: the NOAA table below was
--   registered and is queryable. What does not work is the file-path
--   configuration for a file the platform already holds.
--
--   The platform keeps uploaded files in the NDP file system, which the
--   engine can list:
--     LIST HDFS FILES "/home/zetaris/customer-data/e8706a0413776ba66fde10ebbe767156/file-store" OPTIONS ()
--   -> ["sources.csv", ..., "file:/home/zetaris/customer-data/e8706a0413776ba66fde10ebbe767156/file-store/sources.csv"]
--
--   But every local path form is rejected when the table is created:
--     file:/home/zetaris/customer-data/.../file-store/sources.csv   -> Invalid file path to access
--     file:///home/zetaris/customer-data/.../file-store/sources.csv -> Invalid file path to access
--     /home/zetaris/customer-data/.../file-store/sources.csv       -> Invalid file path to access
--     hdfs://localhost/home/zetaris/.../sources.csv                -> Invalid file path to access
--     ndp://file-store/sources.csv                                 -> Invalid file path to access
--   The same error comes from CREATE FILESTORE SESSION TABLE.
--
--   The platform's own file-store tables all use s3a://, and the storage
--   settings list is empty, so there is no registered local storage to
--   point at:
--     SELECT DISTINCT substring(file_path from '^([a-z0-9]+://)') FROM filestore_table;  -> s3a://
--     GET /api/v1.0/storage-setting -> []
--
--   The documented local-file route is the user interface: NDP File System
--   -> file-store -> upload -> then add the file as a "File Store" table.
--   That route is not reachable from Lightning SQL on this instance.
--
--   So the compiled survey sheet is registered through the REST connector
--   instead (data/registry/03_survey_rest_create.sql). The filestore
--   connector type is still represented in the instance, and the table
--   below proves it works.
--
--   To make this script work for real, the file has to be in a bucket the
--   engine can read with s3a:// and the credentials to read it. That
--   needs an AWS bucket this project does not have, so it is not run.
-- =============================================================================

CREATE LIGHTNING DATABASE CROSS_EXAMINER_FILES DESCRIBE BY "Cross-Examiner file sources - source registry and compiled survey figures";

-- This one works, and it is what proves the filestore connector type is
-- available on this instance. The data is a public NOAA dataset; it is
-- here to exercise the connector, not to feed the evidence.
CREATE LIGHTNING FILESTORE TABLE noaa_ghcn_2025 FROM CROSS_EXAMINER_FILES FORMAT CSV OPTIONS (
  PATH "s3a://noaa-ghcn-pds/csv/by_year/2025.csv",
  inferSchema "true",
  header "false",
  isS3BucketPublic "true",
  useS3PathStyleAccess "true",
  s3Endpoint "s3.us-east-1.amazonaws.com"
);

-- The survey sheet, if a readable bucket ever exists:
--
-- CREATE LIGHTNING FILESTORE TABLE survey_figures FROM CROSS_EXAMINER_FILES FORMAT CSV OPTIONS (
--   PATH "s3a://<bucket>/cross_examiner_survey_figures.csv",
--   header "true",
--   delimiter ",",
--   awsAccessKeyId "<key>",
--   awsSecretAccessKey "<secret>"
-- );
--
-- CACHE TABLE CROSS_EXAMINER_FILES.survey_figures;
--
-- CREATE SCHEMASTORE VIEW survey_figures_table WITH CONTAINER cross_examiner AS
-- SELECT country, antigen, year, measure,
--        CAST(value_percent AS DOUBLE) AS value_percent,
--        source_id AS source_name, source_ref AS source_url, notes
-- FROM cross_examiner_files.survey_figures;

-- =============================================================================
-- Teardown.
-- =============================================================================
-- DROP LIGHTNING DATABASE CROSS_EXAMINER_FILES;

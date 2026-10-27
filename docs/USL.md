# The unified semantic layer

The application never reads a file or an endpoint directly. Everything
comes through one place: the unified layer in Zetaris, or - when that is
not reachable - the same rows from the local files, with the fallback
recorded in the report.

## The vocabulary

Every reported number is one row of one table, whatever it came from.

| Column | Meaning |
|---|---|
| `country` | The country the number is about. |
| `antigen` | The vaccine. |
| `year` | The year the number is about. |
| `measure` | What kind of number it is: `WUENIC estimate`, `Administrative coverage`, `Official (government) coverage`, `Household survey coverage`, `Programme report (synthetic)`. |
| `value_percent` | The number, as a percentage. |
| `source` | The publication it was read from. |
| `source_url` | Where that publication is. |
| `notes` | What the source itself says about it. |

## The source column mapping

Each source publishes a different set of measures, and the registry says
which series each of them belongs to. This is the table that turns a
source column into a unified row.

| Registered source | Its own column | Unified `measure` | Unified origin | Derived from |
|---|---|---|---|---|
| `wuenic_workbook_2025` (XLSX) | `country`, `antigen`, `year`, `mcv1`, target group `si` | `WUENIC estimate` | `wuenic_2025` | - |
| `who_country_profile_2024` (PDF) | row label `estimate` | `WUENIC estimate` | `wuenic_2025` | the workbook |
| `who_country_profile_2024` (PDF) | row label `administrative` | `Administrative coverage` | `cameroon_admin_jrf` | - |
| `who_country_profile_2024` (PDF) | row label `official` | `Official (government) coverage` | `cameroon_government_official` | - |
| `who_country_profile_2024` (PDF) | row label `survey` | `Household survey coverage` | `cameroon_household_survey` | the survey report |
| `dhs_cameroon_2018` (PDF, transcribed) | the measles row of the vaccination table | `Household survey coverage` | `cameroon_dhs_2018` | - |
| `unicef_sdmx_immunisation` (REST/CSV) | `INDICATOR = IM_MCV1`, `TIME_PERIOD`, `OBS_VALUE` | `WUENIC estimate` | `wuenic_2025` | the workbook |
| `worldbank_wdi` (REST/JSON) | `date`, `value` | `WUENIC estimate` | `wuenic_2025` | the workbook |
| `synthetic_programme_reports` (CSV/SQLite) | `value_percent` | `Administrative coverage` | `synthetic_programme` | - |

Normalisations that had to be made:

1. **The workbook uses `mcv1` and `si`**; the layer uses `MCV1` and the
   measure label `WUENIC estimate`.
2. **The country profile uses one page per antigen** with row labels
   (`estimate`, `official`, `administrative`, `survey`); the layer turns
   the row label into the measure label and keeps the year as the column
   header of that table.
3. **The World Bank returns the year as a string** and the value as a
   string; the layer casts the value to a number.
4. **The UNICEF flow returns `AGE = M12T23`**; only that age group is
   the 12-23 month coverage figure the layer holds.
5. **The synthetic rows are administrative coverage** of a fictional
   programme, and they carry `is_synthetic=true` so nothing downstream can
   treat them as evidence.

## The semantic layer

The layer is a USL, not a view with a reassuring name.

| | |
|---|---|
| namespace | `lightning.metastore.cross_examiner` |
| USL | `coverage_observations` |
| table | `coverage_observation` |
| query | `SELECT * FROM lightning.metastore.cross_examiner.coverage_observations.coverage_observation` |

It was created with the documented lifecycle, and every stage is
visible in the instance:

```sql
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.cross_examiner;

COMPILE USL coverage_observations DEPLOY NAMESPACE lightning.metastore.cross_examiner DDL
CREATE TABLE coverage_observation (
  obs_id varchar(200),
  country varchar(100),
  country_iso3 varchar(8),
  antigen varchar(40),
  reporting_year varchar(8),
  measure varchar(100),
  metric_type varchar(60),
  measurement_kind varchar(60),
  value_percent double,
  unit varchar(20),
  denominator varchar(200),
  definition varchar(400),
  source_id varchar(120),
  source_type varchar(40),
  source_name varchar(200),
  source_ref varchar(600),
  origin_id varchar(120),
  origin_label varchar(300),
  derived_from varchar(120),
  is_derived boolean,
  is_synthetic boolean,
  independent_capable boolean,
  verification_scope varchar(40),
  verification_status varchar(40),
  notes varchar(600)
);

ACTIVATE USL TABLE lightning.metastore.cross_examiner.coverage_observations.coverage_observation AS
SELECT concat(...) AS obs_id, country, ... FROM cross_examiner.obs_<source>_<measure>
UNION ALL ...;
```

The activation binds the deployed model to the eight observation views,
one per source and measure, so the layer holds every registered source
with its own lineage.

### The objects in the instance

```
CREATE LIGHTNING DATABASE CROSS_EXAMINER_EVIDENCE ...     -- the published coverage figures
CREATE LIGHTNING DATABASE WUENIC_WORKBOOK ...              -- the workbook extract
CREATE LIGHTNING DATABASE WORLD_BANK_INDICATORS ...       -- the World Bank series
CREATE LIGHTNING DATABASE CROSS_EXAMINER_FILES ...        -- the filestore connector
CREATE LIGHTNING REST TABLE evidence_raw        FROM CROSS_EXAMINER_EVIDENCE REQUEST(endpoint "http://host.docker.internal:8765/evidence", ...)
CREATE LIGHTNING REST TABLE survey_figures_raw  FROM CROSS_EXAMINER_EVIDENCE REQUEST(endpoint "http://host.docker.internal:8765/survey_figures", ...)
CREATE LIGHTNING REST TABLE wuenic_raw          FROM WUENIC_WORKBOOK      REQUEST(endpoint "http://host.docker.internal:8765/wuenic", ...)
CREATE LIGHTNING REST TABLE cmr_measles_coverage FROM WORLD_BANK_INDICATORS REQUEST(endpoint "https://api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS?format=json&per_page=100", ...)
CREATE LIGHTNING FILESTORE TABLE noaa_ghcn_2025 FROM CROSS_EXAMINER_FILES FORMAT CSV OPTIONS (PATH "s3a://noaa-ghcn-pds/csv/by_year/2025.csv", ...)
CREATE DATASOURCE cross_examiner_synthetic OPTIONS (jdbcdriver "org.sqlite.JDBC", jdbcurl "jdbc:sqlite:/home/zetaris/customer-data/shared/cross_examiner_synthetic.db")
REGISTER DATASOURCE TABLE 'synthetic_programme_reports' FROM cross_examiner_synthetic
CREATE SCHEMASTORE CONTAINER cross_examiner
CREATE SCHEMASTORE VIEW evidence_table          ... LATERAL VIEW explode(evidence) AS item
CREATE SCHEMASTORE VIEW wuenic_workbook_table   ... LATERAL VIEW explode(evidence) AS item
CREATE SCHEMASTORE VIEW unified_evidence_table  ... UNION ALL
CREATE OR REPLACE SCHEMASTORE VIEW obs_<source>_<measure> ...   -- 12 of them
COMPILE USL cross_examiner_evidence DDL ... DEPLOY NAMESPACE lightning.metastore
ACTIVATE USL TABLE lightning.metastore.cross_examiner.cross_examiner_evidence AS SELECT ...
COMPILE USL coverage_observations DEPLOY NAMESPACE lightning.metastore.cross_examiner DDL
ACTIVATE USL TABLE lightning.metastore.cross_examiner.coverage_observations.coverage_observation AS ...
```

The exact statements, with the teardown, are in `data/registry/`. The
four USL files are generated from `data/sources.json` by
`scripts/generate_usl_sql.py`.

### Why the unified view drops the estimate rows from the CSV

```sql
SELECT ... FROM cross_examiner.evidence_table WHERE measure <> "WUENIC estimate"
UNION ALL
SELECT ... FROM cross_examiner.wuenic_workbook_table
```

The estimate is taken from the workbook, which is where it comes from, and
the other measures from the published figures. If the estimate were read
from both, every series would be counted twice and the layer would have
no way to tell a duplicate from a second opinion.

This is a label filter, so it depends on the measure labels staying
exactly as they are. The registry in `data/sources.json` is the
authoritative list; the view is the SQL shadow of it.

## The connector types

| Type | Object | Registered? |
|---|---|---|
| REST / JSON | `CROSS_EXAMINER_EVIDENCE.evidence_raw`, `CROSS_EXAMINER_EVIDENCE.survey_figures_raw`, `WUENIC_WORKBOOK.wuenic_raw`, `WORLD_BANK_INDICATORS.cmr_measles_coverage` | yes, all four |
| filestore / CSV | `CROSS_EXAMINER_FILES.noaa_ghcn_2025` | yes - the connector works, but only with `s3a://` paths |
| datasource / SQLite | `cross_examiner_synthetic.synthetic_programme_reports` | yes |

The filestore connector refuses every local path form on this instance
("Invalid file path to access"), so the project's own files cannot be
registered as file tables; the compiled survey sheet goes through the
REST connector instead. The evidence is in
`data/registry/05_survey_filestore_create.sql`.

## The revisions

The country profiles publish the WHO/UNICEF estimates as they stood in
the **2023 revision**; the workbook publishes the **2025 revision**. For
Cameroon the two agree; for Ethiopia they do not (2017: 58 against 59,
2020: 59 against 67), because the estimate was revised.

The registry gives each revision its own origin and the same `series`:

```json
"wuenic_2023": { "series": "wuenic", ... },
"wuenic_2025": { "series": "wuenic", ... }
```

So a revision can neither confirm nor contradict the other: the critic
reports it as a *revision difference*, not a conflict, and it is not
independent confirmation either.

## Verifying the layer

```sh
python3 scripts/verify_usl.py
```

18 checks against the running instance: the object is deployed and
activated, every registered source contributes records, the lineage
survives the unification, the WUENIC estimate and the World Bank's copy
of it share one origin and are counted once, nothing derived is marked
independent, every generated record is marked synthetic, and the
application reads this layer.

`tests/test_usl_offline.py` runs the same rules against fixtures. It
proves the rules, not the instance.

## When the layer is not reachable

`src/evidence_sources.py` reads the same rows from the local files and
records the fallback:

```
- **published_coverage_figures**: 15 records from coverage_evidence.csv (local)
- **compiled_survey_figures**: 1 records from survey_figures.csv (local) — the compiled sheet is not registered as a table yet
```

A run never depends on the registration, and the report never claims more
than it did.

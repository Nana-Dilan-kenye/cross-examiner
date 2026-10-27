# Registering the sources in Zetaris

These are the Lightning SQL statements that register the project's sources
in the unified semantic layer, and the order they have to run in.

**Everything in this folder has been run against the local instance**,
except where a script says otherwise. The statements change the instance,
so each one was dry-run and checked before it ran, one statement at a
time.

## What is in the instance now

| Object | Type | Endpoint |
|---|---|---|
| `CROSS_EXAMINER_EVIDENCE.evidence_raw` | Lightning REST table | `http://host.docker.internal:8765/evidence` |
| `CROSS_EXAMINER_EVIDENCE.survey_figures_raw` | Lightning REST table | `http://host.docker.internal:8765/survey_figures` |
| `WUENIC_WORKBOOK.wuenic_raw` | Lightning REST table | `http://host.docker.internal:8765/wuenic` |
| `WORLD_BANK_INDICATORS.cmr_measles_coverage` | Lightning REST table | `api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS` |
| `CROSS_EXAMINER_FILES.noaa_ghcn_2025` | Lightning filestore table | `s3a://noaa-ghcn-pds/...` |
| `cross_examiner_synthetic.synthetic_programme_reports` | JDBC datasource (SQLite) | the shared volume |
| `cross_examiner.evidence_table` | Schema Store View | over `evidence_raw` |
| `cross_examiner.wuenic_workbook_table` | Schema Store View | over `wuenic_raw` |
| `cross_examiner.unified_evidence_table` | Schema Store View | union of the two |
| `cross_examiner.obs_*` (8 views) | Schema Store View | one per source and measure |
| `lightning.metastore.cross_examiner.cross_examiner_evidence` | USL (pre-existing) | over the unified view |
| `lightning.metastore.cross_examiner.coverage_observations` | **USL (the semantic layer)** | over the 8 observation views |

## The scripts

| Script | Adds | Connector type | State |
|---|---|---|---|
| `01_current_state_create.sql` | the objects that existed before this work | REST | reproduces the earlier instance |
| `02_worldbank_rest_create.sql` | World Bank `SH.IMM.MEAS` for Cameroon | REST / JSON | **registered** |
| `03_survey_rest_create.sql` | the compiled household-survey sheet | REST / JSON | **registered** |
| `04_synthetic_datasource_create.sql` | the generated district returns | datasource / SQLite | **registered** |
| `05_survey_filestore_create.sql` | the filestore route for the sheet | filestore / CSV | **blocked**: the local path form is rejected; the NOAA table proves the connector works |
| `06_usl_views.sql` | one observation view per source and measure | Schema Store View | **registered** (generated) |
| `07_usl_compile.sql` | the USL definition, compiled and deployed | USL | **registered** (generated) |
| `08_usl_activate.sql` | the activation of the USL table | USL | **registered** (generated) |
| `09_usl_verify.sql` | the queries that prove what the layer holds | - | **registered** (generated) |

The four generated files come from `scripts/generate_usl_sql.py`, which
reads `data/sources.json`. The lineage in the layer and the lineage in
the repository therefore cannot drift apart.

## Running them

```sh
cd ~/hackathon/zetaris-getting-started

# always look first
python3 scripts/run_sql.py --dry-run <file>

# one statement at a time, waiting for the result
python3 scripts/run_sql.py -e "CREATE LIGHTNING DATABASE WORLD_BANK_INDICATORS DESCRIBE BY \"...\""
```

The instance's own catalogue, to see what happened:

```sh
python3 scripts/preflight.py
python3 scripts/query_zetaris.py "SHOW LIGHTNING DATABASES"
python3 scripts/query_zetaris.py "SHOW NAMESPACES OR TABLES IN lightning.metastore.cross_examiner"
python3 scripts/query_zetaris.py "SELECT * FROM lightning.metastore.cross_examiner.coverage_observations.coverage_observation"
```

## The rules that apply here

1. **One statement per call.** Lightning SQL, not Spark SQL and not Hive
   SQL. No trailing semicolon.
2. **Dry run first**, then the owner's go-ahead, then the statement.
3. **Never run `docker compose down -v`.** It deletes the metastore and
   the field-encryption keypair, and every stored credential becomes
   unreadable.
4. **Do not call port 8889** on a local instance.
5. **Never print the API key.** It is created by the owner in the Zetaris
   interface.
6. **Do not use the PUDL recipe.** The getting-started repository lists it
   as known to fail.

## The things that did not work, and why

Two connectors are worth a note, because both were tried and both are
recorded here rather than hidden.

### The filestore connector only takes s3a:// on this instance

The connector itself works:

```sql
CREATE LIGHTNING FILESTORE TABLE noaa_ghcn_2025 FROM CROSS_EXAMINER_FILES FORMAT CSV OPTIONS (
  PATH "s3a://noaa-ghcn-pds/csv/by_year/2025.csv", ...);
-- done: 1/1 statements ok
```

What does not work is pointing it at a file the platform already holds.
The files are in the NDP file system and the engine can list them:

```
LIST HDFS FILES "/home/zetaris/customer-data/<org>/file-store" OPTIONS ()
-> ["sources.csv", ..., "file:/home/zetaris/customer-data/<org>/file-store/sources.csv"]
```

but every path form is refused when the table is created:

| Path | Result |
|---|---|
| `file:/home/zetaris/customer-data/.../sources.csv` | Invalid file path to access |
| `file:///home/zetaris/customer-data/.../sources.csv` | Invalid file path to access |
| `/home/zetaris/customer-data/.../sources.csv` | Invalid file path to access |
| `hdfs://localhost/home/zetaris/.../sources.csv` | Invalid file path to access |
| `ndp://file-store/sources.csv` | Invalid file path to access |

`CREATE FILESTORE SESSION TABLE` refuses them the same way. The platform's
own tables all use `s3a://`, and `GET /api/v1.0/storage-setting` returns
`[]`, so there is no registered local storage to point at. The
documented local-file route is the user interface (NDP File System ->
file-store -> upload -> add the file as a File Store table), and Lightning
SQL cannot reach it.

**What was done instead:** the compiled survey sheet is served by the
project's evidence API and registered as a REST table
(`03_survey_rest_create.sql`). The lineage is unchanged.

### The World Bank's answer has to be decoded

The World Bank answers `[meta, data]`. The REST connector does not unwrap
it: the whole response lands in one string column and the schema
inference finds no rows. The documented way out is the companion guide's
pattern, which is what the observation view uses:

```sql
LATERAL VIEW explode(from_json(get_json_object(_corrupt_record, '$[1]'),
  'array<struct<...>>')) AS item
```

The values it returns are 63 for 2020 and 71 for 2023 - the WUENIC
estimate, which is exactly why the registry marks this source as
derived.

## If a source cannot be registered

The application does not depend on the registration. `src/evidence_sources.py`
reads the same rows from the local files when the unified layer cannot be
reached, and the report says which path was used. A source that cannot
be registered is a documented limitation, not a broken build.

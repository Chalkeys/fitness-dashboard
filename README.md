# Fitness Dashboard

A personal fitness management system built with Streamlit and SQLite. The data
layer tracks workouts, body metrics, goals, daily nutrition, and a reusable food
library.

## Data model

The schema in `database/schema.sql` contains:

- `daily_logs`: one ISO-formatted date (`YYYY-MM-DD`) per day, including training,
  energy expenditure, nutrition totals, steps, and notes
- `foods`: personal food definitions, unique by brand and food name
- `nutrition_entries`: meal-level food intake with nutrition snapshots
- workout sessions, exercises, exercise sets, body measurements, and goals

Food quantities support grams, servings, bottles, pieces, and custom units. Total
carbohydrates, dietary fiber, and net carbohydrates are stored separately.

## Setup

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required.

```powershell
uv sync
```

## Initialize the database

Create the tables in the default `fitness.db` file:

```powershell
uv run python scripts/init_db.py
```

Create the tables and import the personal food library in one command:

```powershell
uv run python scripts/init_db.py --seed
```

Both commands are safe to rerun and do not delete existing data. A custom database
path can be supplied with `--database`:

```powershell
uv run python scripts/init_db.py --database data/development.db --seed
```

Generated `.db` files are ignored by Git.

## Maintain and import foods

Add or edit foods in `database/seed_foods.json`, then run:

```powershell
uv run python scripts/seed_foods.py
```

The importer updates foods that have the same brand and food name and inserts new
foods, so repeated imports do not create duplicates. Seed entries with unknown
nutrition labels contain zero values and a verification note; replace those values
with the correct per-default-unit label data before tracking intake.

## Run the tests

```powershell
uv run pytest
```

## Import historical data

Historical records live in human-readable UTF-8 JSON files under `data_sources/`:

- `daily_logs.json`: daily training, energy, macro, and activity totals
- `body_measurements.json`: dated weight, waist, and body-fat measurements
- `nutrition_entries.json`: meal-level food snapshots
- `workouts.json`: nested workouts, exercises, and sets

The exact fields, units, and editing rules are documented in
`data_sources/README.md`. Keep historical records in JSON rather than embedding
them in Python.

Validate all sources without touching the database:

```powershell
uv run python scripts/validate_history.py
```

Preview import statistics without creating or changing a database:

```powershell
uv run python scripts/import_history.py --dry-run
```

Import all sources, or only one source by its file stem:

```powershell
uv run python scripts/import_history.py
uv run python scripts/import_history.py --file daily_logs
uv run python scripts/import_history.py --database data/fitness.db
```

Each import is one transaction. Validation or database errors roll back the whole
run. SHA-256 metadata in `import_runs` skips an unchanged source version, while
stable record keys prevent duplicate nutrition entries and workouts.

After correcting a JSON file, run the normal import again to upsert its changed
records. To clear previously imported history and rebuild it from the selected
source files, use:

```powershell
uv run python scripts/import_history.py --replace
```

`--replace` does not delete the seeded personal food library. Unknown historical
foods are stored as ad hoc database snapshots and are not written to
`database/seed_foods.json`.

## Export Protocol v1

ChatGPT exports belong in `exports/`. Each JSON file is a UTF-8 object with this
envelope:

```json
{
  "protocol": "fitness-dashboard-export-v1",
  "history_version": "2026-08-03-v1",
  "review_status": "approved",
  "exported_at": "2026-08-03T18:00:00Z",
  "daily_logs": [],
  "body_measurements": [],
  "nutrition_entries": [],
  "workouts": [],
  "foods": []
}
```

`history_version` should start with an ISO date and increase for a corrected
export of the same day. The importer processes versions in order and does not let
an older version overwrite a newer one. Every record is UPSERTed; source hashes
and stable keys prevent duplicates. Files with `review_status` other than
`approved` are recorded as skipped. `import_log` stores filename, SHA-256,
import time, new/modified/skipped/failed counts, and status.

Validate or import a directory of exports:

```powershell
uv run python scripts/validate_export.py exports\*.json
uv run python scripts/import_exports.py exports\ --dry-run
uv run python scripts/import_exports.py exports\
uv run python scripts/import_exports.py exports\ --since 2026-08-01 --file export.json
uv run python scripts/import_exports.py exports\ --replace
```

`imports/` and `archive/` are reserved for import reports and retained source
files; they are never scanned as export input.

## Daily Export Protocol v1 (canonical)

Milestone 4B standardizes new data as one JSON document per day under `exports/`:

```text
exports/day-001.json
exports/day-002.json
exports/2026-08-03.json
```

The complete contract is documented in [docs/export_protocol_v1.md](<H:/My Projects/fitness-dashboard/docs/export_protocol_v1.md>) and enforced by
[schemas/daily_export_v1.schema.json](<H:/My Projects/fitness-dashboard/schemas/daily_export_v1.schema.json>). Required envelope fields include `protocol_version: "1.0"`, `export_id`, positive integer `history_version`, `date`/`day_number`, provenance, body, daily log, nutrition, workout, and review.

Validate all daily files, emit machine-readable output, or treat warnings as
failures:

```powershell
uv run python scripts/validate_exports.py
uv run python scripts/validate_exports.py --json
uv run python scripts/validate_exports.py --strict
```

Import uses one transaction per file, so one bad export does not block other
files:

```powershell
uv run python scripts/import_exports.py
uv run python scripts/import_exports.py --dry-run
uv run python scripts/import_exports.py --include-needs-review
uv run python scripts/import_exports.py --file exports/2026-08-03.json
uv run python scripts/import_exports.py --since 2026-07-01
uv run python scripts/import_exports.py --replace
```

Approved dated exports enter formal tables. A `date: null` export is retained in
`staged_daily_exports` and never creates a formal daily log. `review_status` values
other than `approved` are skipped unless `--include-needs-review` is supplied.
Re-exporting the same `export_id` with a higher `history_version` replaces the
older version; the original JSON remains in `exports/` and can be copied to
`archive/` manually. Legacy `data_sources/` files remain supported and can be
converted without guessing dates:

```powershell
uv run python scripts/convert_legacy_history.py --dry-run
uv run python scripts/convert_legacy_history.py
```

## Run the dashboard

Once a Streamlit entry point such as `app.py` is added:

```powershell
uv run streamlit run app.py
```

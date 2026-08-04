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

## Run the dashboard

Once a Streamlit entry point such as `app.py` is added:

```powershell
uv run streamlit run app.py
```

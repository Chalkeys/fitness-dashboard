# Fitness Dashboard

A Streamlit fitness dashboard backed by SQLite. The first database layer records
daily measurements, workout sessions and sets, food intake, and nutrition totals.

## Data model

The normalized schema in `database/schema.sql` contains:

- `daily_logs`: one row per ISO-formatted calendar date (`YYYY-MM-DD`)
- `body_measurements`: optional measurements for a daily log
- `workout_sessions`, `exercises`, and `exercise_sets`: workout tracking
- `foods` and `nutrition_entries`: food definitions and daily consumption
- `nutrition_daily_totals`: daily calories and macronutrient totals

Food quantities support grams, servings, bottles, pieces, and named custom units.
Total carbohydrates, dietary fiber, and net carbohydrates are stored separately.
SQLite foreign keys and validation constraints protect relationships and values.

## Setup

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required.

```powershell
uv sync
```

## Initialize the database

Run the idempotent initializer from the repository root:

```powershell
uv run python database/init_db.py
```

This creates `fitness.db`, enables foreign-key enforcement for the initializer
connection, and prints all application tables. Re-running the command adds any
missing schema objects without deleting existing data. To choose another path:

```powershell
uv run python database/init_db.py --database data/development.db
```

Generated `.db` files are ignored by Git.

## Run the tests

```powershell
uv run python -m unittest discover -s tests -v
```

## Run the dashboard

Once a Streamlit entry point such as `app.py` is added:

```powershell
uv run streamlit run app.py
```

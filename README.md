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
uv run python -m unittest discover -s tests -v
```

## Run the dashboard

Once a Streamlit entry point such as `app.py` is added:

```powershell
uv run streamlit run app.py
```

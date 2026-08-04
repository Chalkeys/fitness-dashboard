# Fitness Dashboard

A Streamlit dashboard foundation for recording workouts, tracking body
measurements, and monitoring fitness goals with SQLite.

## Data model

The schema in `database/schema.sql` contains:

- `exercises`: reusable exercise definitions
- `workouts`: dated training sessions
- `workout_sets`: strength, distance, or duration results within a workout
- `body_measurements`: body weight, body-fat, and waist history
- `goals`: metric targets and their status

SQLite foreign keys, validation constraints, and indexes are included. Dates and
timestamps are stored as ISO 8601 text so they work naturally with SQLite and
pandas.

## Setup

Python 3.11 or newer is recommended.

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
py -3 scripts/init_db.py
```

The initializer creates `data/fitness.db`. It is safe to run more than once and
also accepts a custom location:

```powershell
py -3 scripts/init_db.py --database data/test.db
```

The local database is ignored by Git. The Streamlit application can use
`scripts.init_db.initialize_database()` at startup to ensure the schema exists.

## Run the dashboard

Once a Streamlit entry point such as `app.py` is added, run it with:

```powershell
streamlit run app.py
```

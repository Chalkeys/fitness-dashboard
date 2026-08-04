# Historical data sources

These UTF-8 JSON files are the editable source of truth for historical imports.
Keep the files indented and human-readable so corrections can be reviewed in Git.

- `daily_logs.json`: one record per date; nullable metrics are allowed.
- `body_measurements.json`: dated weight, waist, and body-fat measurements.
- `nutrition_entries.json`: meal-level food snapshots linked by brand and name.
- `workouts.json`: nested workouts, exercises, and sets.

Dates must use `YYYY-MM-DD`. Nutrition values use grams and energy values use
kilocalories. Weight and waist values use kilograms and centimeters. Exercise
weights use kilograms and distances use meters.

Validate edits before importing:

```powershell
uv run python scripts/validate_history.py
```

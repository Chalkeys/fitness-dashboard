# Daily Export Protocol v1

Milestone 4B uses one UTF-8 JSON document per day. Put pending files in
`exports/`; successful imports leave the source file in place. Older files may be
copied to `archive/` manually.

## Envelope

Each file must contain `protocol_version: "1.0"`, a stable `export_id`, a
positive integer `history_version`, an ISO timestamp `exported_at`, and exactly
one daily payload. `date` and `day_number` may be null individually, but never
both. A date-less export is stored in `staged_daily_exports` until it is assigned
a date; it never creates a formal `daily_logs` row.

`provenance.confidence` is `low`, `medium`, or `high`. Review entries use
`approved`, `needs_review`, or `rejected`. By default only approved exports enter
formal tables; pass `--include-needs-review` to import needs-review data.

Nutrition `entry_id` values are unique within a file and become unique per
`export_id`. Workout `session_id` values are unique per `export_id`. Re-exporting
the same `export_id` with a larger `history_version` replaces its prior rows.
Identical file hashes are skipped.

## Naming

Use `day-001.json`, `day-002.json`, or `YYYY-MM-DD.json`. The validator checks a
numeric day filename against `day_number` and a date filename against `date`.

## Commands

```powershell
uv run python scripts/validate_exports.py
uv run python scripts/validate_exports.py exports/2026-08-03.json --strict
uv run python scripts/validate_exports.py --json
uv run python scripts/import_exports.py
uv run python scripts/import_exports.py --dry-run
uv run python scripts/import_exports.py --include-needs-review
uv run python scripts/import_exports.py --file exports/day-001.json
uv run python scripts/import_exports.py --since 2026-07-01
uv run python scripts/import_exports.py --replace
```

Validation differences such as calorie-balance or nutrition-total mismatches are
warnings. `--strict` promotes warnings to a non-zero validation result; imports
still never overwrite a daily log merely because a warning exists.

## Legacy conversion

`data_sources/` remains supported by `scripts/import_history.py`. To convert
legacy records without inventing dates:

```powershell
uv run python scripts/convert_legacy_history.py --dry-run
uv run python scripts/convert_legacy_history.py
```

Records without an explicit date are reported and omitted. Source files are never
deleted.

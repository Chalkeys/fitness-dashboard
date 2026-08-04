PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    category TEXT NOT NULL,
    muscle_group TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    workout_date TEXT NOT NULL,
    name TEXT,
    duration_minutes INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workout_sets (
    id INTEGER PRIMARY KEY,
    workout_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    set_number INTEGER NOT NULL CHECK (set_number > 0),
    reps INTEGER CHECK (reps IS NULL OR reps >= 0),
    weight REAL CHECK (weight IS NULL OR weight >= 0),
    distance REAL CHECK (distance IS NULL OR distance >= 0),
    duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    notes TEXT,
    FOREIGN KEY (workout_id) REFERENCES workouts (id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises (id),
    UNIQUE (workout_id, exercise_id, set_number)
);

CREATE TABLE IF NOT EXISTS body_measurements (
    id INTEGER PRIMARY KEY,
    measured_at TEXT NOT NULL,
    weight REAL CHECK (weight IS NULL OR weight > 0),
    body_fat_percentage REAL CHECK (
        body_fat_percentage IS NULL
        OR body_fat_percentage BETWEEN 0 AND 100
    ),
    waist REAL CHECK (waist IS NULL OR waist > 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    metric TEXT NOT NULL,
    target_value REAL NOT NULL,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts (workout_date);
CREATE INDEX IF NOT EXISTS idx_workout_sets_workout ON workout_sets (workout_id);
CREATE INDEX IF NOT EXISTS idx_measurements_date ON body_measurements (measured_at);

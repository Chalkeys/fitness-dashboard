PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS daily_logs (
    id INTEGER PRIMARY KEY,
    log_date TEXT NOT NULL UNIQUE
        CHECK (log_date = date(log_date) AND length(log_date) = 10),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS body_measurements (
    id INTEGER PRIMARY KEY,
    daily_log_id INTEGER NOT NULL UNIQUE,
    weight_kg REAL CHECK (weight_kg IS NULL OR weight_kg > 0),
    body_fat_percentage REAL CHECK (
        body_fat_percentage IS NULL
        OR body_fat_percentage BETWEEN 0 AND 100
    ),
    waist_cm REAL CHECK (waist_cm IS NULL OR waist_cm > 0),
    resting_heart_rate INTEGER CHECK (
        resting_heart_rate IS NULL OR resting_heart_rate > 0
    ),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_log_id) REFERENCES daily_logs (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id INTEGER PRIMARY KEY,
    daily_log_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    started_at TEXT,
    duration_minutes INTEGER CHECK (
        duration_minutes IS NULL OR duration_minutes >= 0
    ),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_log_id) REFERENCES daily_logs (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    category TEXT NOT NULL,
    muscle_group TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exercise_sets (
    id INTEGER PRIMARY KEY,
    workout_session_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    set_number INTEGER NOT NULL CHECK (set_number > 0),
    reps INTEGER CHECK (reps IS NULL OR reps >= 0),
    weight_kg REAL CHECK (weight_kg IS NULL OR weight_kg >= 0),
    distance_meters REAL CHECK (
        distance_meters IS NULL OR distance_meters >= 0
    ),
    duration_seconds INTEGER CHECK (
        duration_seconds IS NULL OR duration_seconds >= 0
    ),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workout_session_id)
        REFERENCES workout_sessions (id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises (id),
    UNIQUE (workout_session_id, exercise_id, set_number)
);

CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    brand TEXT,
    serving_quantity REAL NOT NULL DEFAULT 1 CHECK (serving_quantity > 0),
    serving_unit TEXT NOT NULL CHECK (
        serving_unit IN ('grams', 'servings', 'bottles', 'pieces', 'custom')
    ),
    custom_unit_name TEXT,
    calories_per_serving REAL NOT NULL DEFAULT 0
        CHECK (calories_per_serving >= 0),
    protein_g_per_serving REAL NOT NULL DEFAULT 0
        CHECK (protein_g_per_serving >= 0),
    total_carbohydrates_g_per_serving REAL NOT NULL DEFAULT 0
        CHECK (total_carbohydrates_g_per_serving >= 0),
    dietary_fiber_g_per_serving REAL NOT NULL DEFAULT 0
        CHECK (dietary_fiber_g_per_serving >= 0),
    net_carbohydrates_g_per_serving REAL NOT NULL DEFAULT 0
        CHECK (net_carbohydrates_g_per_serving >= 0),
    fat_g_per_serving REAL NOT NULL DEFAULT 0
        CHECK (fat_g_per_serving >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (serving_unit = 'custom' AND custom_unit_name IS NOT NULL)
        OR (serving_unit <> 'custom' AND custom_unit_name IS NULL)
    ),
    CHECK (dietary_fiber_g_per_serving <= total_carbohydrates_g_per_serving),
    CHECK (net_carbohydrates_g_per_serving <= total_carbohydrates_g_per_serving)
);

CREATE TABLE IF NOT EXISTS nutrition_entries (
    id INTEGER PRIMARY KEY,
    daily_log_id INTEGER NOT NULL,
    food_id INTEGER NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL CHECK (
        unit IN ('grams', 'servings', 'bottles', 'pieces', 'custom')
    ),
    custom_unit_name TEXT,
    servings_equivalent REAL CHECK (
        servings_equivalent IS NULL OR servings_equivalent > 0
    ),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_log_id) REFERENCES daily_logs (id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods (id),
    CHECK (
        (unit = 'custom' AND custom_unit_name IS NOT NULL)
        OR (unit <> 'custom' AND custom_unit_name IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS nutrition_daily_totals (
    id INTEGER PRIMARY KEY,
    daily_log_id INTEGER NOT NULL UNIQUE,
    calories REAL NOT NULL DEFAULT 0 CHECK (calories >= 0),
    protein_g REAL NOT NULL DEFAULT 0 CHECK (protein_g >= 0),
    total_carbohydrates_g REAL NOT NULL DEFAULT 0
        CHECK (total_carbohydrates_g >= 0),
    dietary_fiber_g REAL NOT NULL DEFAULT 0 CHECK (dietary_fiber_g >= 0),
    net_carbohydrates_g REAL NOT NULL DEFAULT 0
        CHECK (net_carbohydrates_g >= 0),
    fat_g REAL NOT NULL DEFAULT 0 CHECK (fat_g >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_log_id) REFERENCES daily_logs (id) ON DELETE CASCADE,
    CHECK (dietary_fiber_g <= total_carbohydrates_g),
    CHECK (net_carbohydrates_g <= total_carbohydrates_g)
);

CREATE INDEX IF NOT EXISTS idx_workout_sessions_daily_log
    ON workout_sessions (daily_log_id);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_session
    ON exercise_sets (workout_session_id);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_exercise
    ON exercise_sets (exercise_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_entries_daily_log
    ON nutrition_entries (daily_log_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_entries_food
    ON nutrition_entries (food_id);

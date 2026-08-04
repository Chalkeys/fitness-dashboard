PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS daily_logs (
    id INTEGER PRIMARY KEY,
    log_date TEXT NOT NULL UNIQUE
        CHECK (log_date = date(log_date) AND length(log_date) = 10),
    is_training_day INTEGER NOT NULL DEFAULT 0
        CHECK (is_training_day IN (0, 1)),
    training_type TEXT,
    calories_intake REAL NOT NULL DEFAULT 0 CHECK (calories_intake >= 0),
    tdee REAL NOT NULL DEFAULT 0 CHECK (tdee >= 0),
    calorie_balance REAL NOT NULL DEFAULT 0,
    protein_g REAL NOT NULL DEFAULT 0 CHECK (protein_g >= 0),
    total_carbs_g REAL NOT NULL DEFAULT 0 CHECK (total_carbs_g >= 0),
    fiber_g REAL NOT NULL DEFAULT 0 CHECK (fiber_g >= 0),
    net_carbs_g REAL NOT NULL DEFAULT 0 CHECK (net_carbs_g >= 0),
    fat_g REAL NOT NULL DEFAULT 0 CHECK (fat_g >= 0),
    steps INTEGER NOT NULL DEFAULT 0 CHECK (steps >= 0),
    active_energy REAL NOT NULL DEFAULT 0 CHECK (active_energy >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (fiber_g <= total_carbs_g),
    CHECK (net_carbs_g <= total_carbs_g),
    CHECK (is_training_day = 1 OR training_type IS NULL)
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

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    metric TEXT NOT NULL,
    target_value REAL NOT NULL,
    target_date TEXT CHECK (
        target_date IS NULL
        OR (target_date = date(target_date) AND length(target_date) = 10)
    ),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY,
    food_name TEXT NOT NULL COLLATE NOCASE,
    brand TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
    default_unit TEXT NOT NULL CHECK (
        default_unit IN ('g', 'serving', 'bottle', 'piece', 'custom')
    ),
    calories REAL NOT NULL DEFAULT 0 CHECK (calories >= 0),
    protein_g REAL NOT NULL DEFAULT 0 CHECK (protein_g >= 0),
    total_carbs_g REAL NOT NULL DEFAULT 0 CHECK (total_carbs_g >= 0),
    fiber_g REAL NOT NULL DEFAULT 0 CHECK (fiber_g >= 0),
    net_carbs_g REAL NOT NULL DEFAULT 0 CHECK (net_carbs_g >= 0),
    fat_g REAL NOT NULL DEFAULT 0 CHECK (fat_g >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brand, food_name),
    CHECK (fiber_g <= total_carbs_g),
    CHECK (net_carbs_g <= total_carbs_g)
);

CREATE TABLE IF NOT EXISTS nutrition_entries (
    id INTEGER PRIMARY KEY,
    log_date TEXT NOT NULL
        CHECK (log_date = date(log_date) AND length(log_date) = 10),
    meal_type TEXT NOT NULL CHECK (length(trim(meal_type)) > 0),
    food_id INTEGER NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    unit TEXT NOT NULL CHECK (
        unit IN ('g', 'serving', 'bottle', 'piece', 'custom')
    ),
    calories REAL NOT NULL DEFAULT 0 CHECK (calories >= 0),
    protein_g REAL NOT NULL DEFAULT 0 CHECK (protein_g >= 0),
    carbs_g REAL NOT NULL DEFAULT 0 CHECK (carbs_g >= 0),
    fiber_g REAL NOT NULL DEFAULT 0 CHECK (fiber_g >= 0),
    fat_g REAL NOT NULL DEFAULT 0 CHECK (fat_g >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_date) REFERENCES daily_logs (log_date) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods (id),
    CHECK (fiber_g <= carbs_g)
);

CREATE INDEX IF NOT EXISTS idx_workout_sessions_daily_log
    ON workout_sessions (daily_log_id);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_session
    ON exercise_sets (workout_session_id);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_exercise
    ON exercise_sets (exercise_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_entries_date
    ON nutrition_entries (log_date);
CREATE INDEX IF NOT EXISTS idx_nutrition_entries_food
    ON nutrition_entries (food_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_entries_meal
    ON nutrition_entries (log_date, meal_type);

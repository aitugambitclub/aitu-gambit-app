-- ============================================================
-- Схема базы данных для университетского игрового клуба (AITU)
-- PostgreSQL (например, на Supabase — бесплатный тариф)
-- ============================================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,        -- Telegram user id
    corp_email TEXT UNIQUE NOT NULL,           -- 000000@astanait.edu.kz
    is_verified BOOLEAN DEFAULT FALSE,         -- подтвердил email кодом
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE email_verification_codes (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    code TEXT NOT NULL,                        -- 6-значный код
    expires_at TIMESTAMPTZ NOT NULL,           -- код живёт ~10 минут
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE profiles (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL,             -- уникальный, меняется раз в 30 дней
    username_changed_at TIMESTAMPTZ DEFAULT now(),
    display_name TEXT NOT NULL,                -- любое, дублируется, меняется раз в 15 дней
    display_name_changed_at TIMESTAMPTZ DEFAULT now(),
    course INT,                                -- 1, 2, 3 (курс)
    admission_year INT,                        -- год поступления — доп. сигнал для мэтчинга
    specialty TEXT,                            -- напр. "Software Engineering"
    bio TEXT,                                  -- описание, по желанию
    open_to_connect BOOLEAN DEFAULT FALSE,     -- согласие участвовать в "знакомствах"
    rating INT DEFAULT 1200,                   -- базовый Elo
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ---------- Игры и матчи ----------

CREATE TABLE games (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,                 -- 'checkers', 'chess', ...
    name TEXT NOT NULL
);

CREATE TABLE matches (
    id BIGSERIAL PRIMARY KEY,
    game_id INT REFERENCES games(id),
    player1_id BIGINT REFERENCES users(id),
    player2_id BIGINT REFERENCES users(id),
    winner_id BIGINT REFERENCES users(id),     -- NULL = ничья/не завершён
    state JSONB,                               -- текущее состояние доски
    status TEXT DEFAULT 'active',              -- active / finished / abandoned
    created_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

-- ---------- Турниры ----------

CREATE TABLE tournaments (
    id SERIAL PRIMARY KEY,
    game_id INT REFERENCES games(id),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'upcoming',            -- upcoming / active / finished
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ
);

CREATE TABLE tournament_participants (
    tournament_id INT REFERENCES tournaments(id),
    user_id BIGINT REFERENCES users(id),
    PRIMARY KEY (tournament_id, user_id)
);

-- ---------- Достижения ----------

CREATE TABLE badges (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,                 -- 'first_win', 'streak_10'
    name TEXT NOT NULL
);

CREATE TABLE user_badges (
    user_id BIGINT REFERENCES users(id),
    badge_id INT REFERENCES badges(id),
    earned_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, badge_id)
);

-- ---------- "Хочешь общаться?" (без чатов внутри бота) ----------

CREATE TABLE connect_requests (
    id BIGSERIAL PRIMARY KEY,
    from_user_id BIGINT REFERENCES users(id),
    to_user_id BIGINT REFERENCES users(id),
    status TEXT DEFAULT 'pending',             -- pending / accepted / declined
    created_at TIMESTAMPTZ DEFAULT now(),
    responded_at TIMESTAMPTZ,
    UNIQUE (from_user_id, to_user_id)
);
-- Когда status='accepted' у обеих сторон — бот один раз присылает
-- обоим настоящие @username из Telegram, дальше общение уже вне бота.

-- pricewatch schema (Postgres)

CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL PRIMARY KEY,
    telegram_id  BIGINT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    asin          TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    last_seen_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS trackings (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asin           TEXT NOT NULL REFERENCES products(asin),
    threshold_pct  NUMERIC NOT NULL DEFAULT 50 CHECK (threshold_pct BETWEEN 1 AND 95),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, asin)
);

-- Empty set for a user means "all categories".
CREATE TABLE IF NOT EXISTS user_categories (
    user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category  TEXT NOT NULL,
    PRIMARY KEY (user_id, category)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    asin         TEXT NOT NULL REFERENCES products(asin),
    price        NUMERIC NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'INR',
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_asin_time
    ON price_snapshots (asin, captured_at DESC);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id           BIGSERIAL PRIMARY KEY,
    tracking_id  BIGINT NOT NULL REFERENCES trackings(id) ON DELETE CASCADE,
    price        NUMERIC NOT NULL,
    baseline     NUMERIC NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts_tracking_time
    ON alerts_sent (tracking_id, sent_at DESC);

-- Deals relayed from a watched Telegram channel (channelwatch.py).
-- UNIQUE(asin) de-dupes repeated posts of the same product.
CREATE TABLE IF NOT EXISTS channel_deals (
    id             BIGSERIAL PRIMARY KEY,
    channel_msg_id BIGINT NOT NULL,
    asin           TEXT NOT NULL,
    category       TEXT NOT NULL DEFAULT '',
    relayed_to     INT NOT NULL DEFAULT 0,
    seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asin)
);

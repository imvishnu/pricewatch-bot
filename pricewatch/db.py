"""Thin database layer — ALL SQL lives here (psycopg v3).

Every other module calls these functions; no raw SQL elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from .compare import BASELINE_WINDOW_DAYS


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=True)


# --- users -----------------------------------------------------------------

def upsert_user(conn: psycopg.Connection, telegram_id: int) -> int:
    row = conn.execute(
        """
        INSERT INTO users (telegram_id) VALUES (%s)
        ON CONFLICT (telegram_id) DO UPDATE SET telegram_id = EXCLUDED.telegram_id
        RETURNING id
        """,
        (telegram_id,),
    ).fetchone()
    return row["id"]


def get_user_id(conn: psycopg.Connection, telegram_id: int) -> int | None:
    row = conn.execute("SELECT id FROM users WHERE telegram_id = %s",
                       (telegram_id,)).fetchone()
    return row["id"] if row else None


# --- categories ------------------------------------------------------------

def set_user_categories(conn: psycopg.Connection, user_id: int,
                        categories: list[str]) -> None:
    with conn.transaction():
        conn.execute("DELETE FROM user_categories WHERE user_id = %s", (user_id,))
        for cat in categories:
            conn.execute(
                "INSERT INTO user_categories (user_id, category) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (user_id, cat),
            )


def get_user_categories(conn: psycopg.Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT category FROM user_categories WHERE user_id = %s ORDER BY category",
        (user_id,),
    ).fetchall()
    return [r["category"] for r in rows]


# --- products & trackings ---------------------------------------------------

def upsert_product(conn: psycopg.Connection, asin: str,
                   title: str = "", category: str = "") -> None:
    conn.execute(
        """
        INSERT INTO products (asin, title, category, last_seen_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (asin) DO UPDATE SET
            title = CASE WHEN EXCLUDED.title <> '' THEN EXCLUDED.title
                         ELSE products.title END,
            category = CASE WHEN EXCLUDED.category <> '' THEN EXCLUDED.category
                            ELSE products.category END,
            last_seen_at = now()
        """,
        (asin, title, category),
    )


def upsert_tracking(conn: psycopg.Connection, user_id: int, asin: str,
                    threshold_pct: float) -> None:
    conn.execute(
        """
        INSERT INTO trackings (user_id, asin, threshold_pct, active)
        VALUES (%s, %s, %s, TRUE)
        ON CONFLICT (user_id, asin) DO UPDATE
            SET threshold_pct = EXCLUDED.threshold_pct, active = TRUE
        """,
        (user_id, asin, threshold_pct),
    )


def list_trackings_for_user(conn: psycopg.Connection, user_id: int) -> list[dict]:
    return conn.execute(
        """
        SELECT t.asin, t.threshold_pct, p.title, p.category
        FROM trackings t JOIN products p USING (asin)
        WHERE t.user_id = %s AND t.active
        ORDER BY t.created_at
        """,
        (user_id,),
    ).fetchall()


@dataclass(frozen=True)
class ActiveTracking:
    tracking_id: int
    asin: str
    threshold_pct: float
    telegram_id: int
    user_id: int


def list_active_trackings(conn: psycopg.Connection) -> list[ActiveTracking]:
    rows = conn.execute(
        """
        SELECT t.id AS tracking_id, t.asin, t.threshold_pct, t.user_id,
               u.telegram_id
        FROM trackings t JOIN users u ON u.id = t.user_id
        WHERE t.active
        ORDER BY t.asin
        """,
    ).fetchall()
    return [ActiveTracking(r["tracking_id"], r["asin"], float(r["threshold_pct"]),
                           r["telegram_id"], r["user_id"]) for r in rows]


# --- snapshots & alerts ------------------------------------------------------

def add_snapshot(conn: psycopg.Connection, asin: str, price: float,
                 currency: str) -> None:
    conn.execute(
        "INSERT INTO price_snapshots (asin, price, currency) VALUES (%s, %s, %s)",
        (asin, price, currency),
    )


def recent_prices(conn: psycopg.Connection, asin: str) -> list[float]:
    """Prices within the trailing baseline window (90 days), oldest first."""
    rows = conn.execute(
        """
        SELECT price FROM price_snapshots
        WHERE asin = %s AND captured_at >= now() - make_interval(days => %s)
        ORDER BY captured_at
        """,
        (asin, BASELINE_WINDOW_DAYS),
    ).fetchall()
    return [float(r["price"]) for r in rows]


def last_alerted_price(conn: psycopg.Connection, tracking_id: int) -> float | None:
    row = conn.execute(
        """
        SELECT price FROM alerts_sent
        WHERE tracking_id = %s ORDER BY sent_at DESC LIMIT 1
        """,
        (tracking_id,),
    ).fetchone()
    return float(row["price"]) if row else None


def record_alert(conn: psycopg.Connection, tracking_id: int, price: float,
                 baseline: float) -> None:
    conn.execute(
        "INSERT INTO alerts_sent (tracking_id, price, baseline) VALUES (%s, %s, %s)",
        (tracking_id, price, baseline),
    )

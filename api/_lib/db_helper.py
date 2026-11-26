"""PostgreSQL database helper for Neon (with in-memory fallback for local testing)."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - allows offline unit testing without psycopg2
    psycopg2 = None
    RealDictCursor = None

DEFAULT_MENU: list[dict[str, Any]] = [
    {"item_id": 1, "name": "Momo", "price": 149.99},
    {"item_id": 2, "name": "Thukpa", "price": 99.99},
    {"item_id": 3, "name": "Dal Bhat", "price": 199.99},
    {"item_id": 4, "name": "Sel Roti", "price": 89.99},
    {"item_id": 5, "name": "Chowmein", "price": 129.99},
    {"item_id": 6, "name": "Gundruk", "price": 79.99},
    {"item_id": 7, "name": "Aloo Tama", "price": 159.99},
    {"item_id": 8, "name": "Sekuwa", "price": 249.99},
    {"item_id": 9, "name": "Juju Dhau", "price": 99.99},
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS food_items (
    item_id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL REFERENCES food_items(item_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    total_price NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (order_id, item_id)
);

CREATE TABLE IF NOT EXISTS order_tracking (
    order_id INTEGER PRIMARY KEY,
    status VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(128) PRIMARY KEY,
    context VARCHAR(64),
    inprogress_order JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO food_items (item_id, name, price) VALUES
    (1, 'Momo', 149.99),
    (2, 'Thukpa', 99.99),
    (3, 'Dal Bhat', 199.99),
    (4, 'Sel Roti', 89.99),
    (5, 'Chowmein', 129.99),
    (6, 'Gundruk', 79.99),
    (7, 'Aloo Tama', 159.99),
    (8, 'Sekuwa', 249.99),
    (9, 'Juju Dhau', 99.99)
ON CONFLICT (item_id) DO NOTHING;

INSERT INTO order_tracking (order_id, status) VALUES
    (40, 'delivered'),
    (41, 'in transit'),
    (42, 'in progress')
ON CONFLICT (order_id) DO NOTHING;

INSERT INTO orders (order_id, item_id, quantity, total_price) VALUES
    (40, 1, 2, 299.98),
    (40, 3, 1, 199.99),
    (41, 4, 3, 269.97),
    (41, 6, 2, 159.98),
    (41, 9, 4, 399.96),
    (42, 1, 2, 299.98),
    (42, 8, 1, 249.99)
ON CONFLICT (order_id, item_id) DO NOTHING;
"""

_schema_initialized = False

# In-memory fallback used only when DATABASE_URL is not configured (e.g., local demo/tests)
_mem_sessions: dict[str, dict[str, Any]] = {}
_mem_orders: dict[int, list[dict[str, Any]]] = {
    40: [{"name": "Momo", "quantity": 2, "total_price": 299.98}, {"name": "Dal Bhat", "quantity": 1, "total_price": 199.99}],
    41: [{"name": "Sel Roti", "quantity": 3, "total_price": 269.97}],
    42: [{"name": "Momo", "quantity": 2, "total_price": 299.98}],
}
_mem_tracking: dict[int, str] = {
    40: "delivered",
    41: "in transit",
    42: "in progress",
}


def get_database_url() -> str | None:
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if url:
        return url.strip()
    return None


def is_postgres_configured() -> bool:
    return bool(get_database_url() and psycopg2 is not None)


@contextmanager
def get_connection():
    database_url = get_database_url()
    if not database_url or psycopg2 is None:
        raise RuntimeError("PostgreSQL is not configured")

    kwargs: dict[str, Any] = {"connect_timeout": 10}
    if "sslmode=" not in database_url:
        kwargs["sslmode"] = "require"

    conn = psycopg2.connect(database_url, **kwargs)
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema() -> None:
    """Create tables and seed default data once per warm container."""
    global _schema_initialized
    if _schema_initialized or not is_postgres_configured():
        return

    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    _schema_initialized = True


def check_health() -> dict[str, Any]:
    """Return database connectivity status for /api/health."""
    if not is_postgres_configured():
        return {
            "database": "in-memory-fallback",
            "connected": False,
            "note": "Set DATABASE_URL to connect to Neon PostgreSQL",
        }
    try:
        ensure_schema()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM food_items")
                menu_count = cur.fetchone()[0]
        return {
            "database": "neon-postgres",
            "connected": True,
            "menu_items": menu_count,
        }
    except Exception as exc:
        return {
            "database": "neon-postgres",
            "connected": False,
            "error": str(exc),
        }


def get_menu_items() -> list[dict[str, Any]]:
    if not is_postgres_configured():
        return list(DEFAULT_MENU)

    ensure_schema()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT item_id, name, price FROM food_items ORDER BY item_id")
            rows = cur.fetchall()
            return [
                {"item_id": r["item_id"], "name": r["name"], "price": float(r["price"])}
                for r in rows
            ]


def get_session(session_id: str) -> tuple[str | None, dict[str, int]]:
    """Return (context, inprogress_order) for a session."""
    if not is_postgres_configured():
        data = _mem_sessions.get(session_id)
        if not data:
            return None, {}
        return data.get("context"), dict(data.get("inprogress_order", {}))

    ensure_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT context, inprogress_order FROM chat_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None, {}
            context, order_json = row
            if isinstance(order_json, str):
                order_json = json.loads(order_json)
            order = {str(k): int(v) for k, v in (order_json or {}).items()}
            return context, order


def save_session(session_id: str, context: str | None, inprogress_order: dict[str, int]) -> None:
    """Persist dialogue context and in-progress cart for serverless statelessness."""
    clean_order = {str(k): int(v) for k, v in inprogress_order.items() if int(v) > 0}
    if not is_postgres_configured():
        _mem_sessions[session_id] = {
            "context": context,
            "inprogress_order": clean_order,
        }
        return

    ensure_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_sessions (session_id, context, inprogress_order, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    context = EXCLUDED.context,
                    inprogress_order = EXCLUDED.inprogress_order,
                    updated_at = NOW()
                """,
                (session_id, context, json.dumps(clean_order)),
            )
        conn.commit()


def save_order(order: dict[str, int]) -> tuple[int, float]:
    """
    Save an order transactionally and return (order_id, total_price).
    Replaces the legacy MySQL stored procedures with standard parameterized SQL.
    """
    if not order:
        raise ValueError("Cannot save an empty order")

    if not is_postgres_configured():
        price_map = {item["name"].lower(): Decimal(str(item["price"])) for item in DEFAULT_MENU}
        next_id = max(_mem_tracking.keys(), default=40) + 1
        total = Decimal("0.00")
        items_saved = []
        for food_name, qty in order.items():
            unit_price = price_map.get(food_name.lower())
            if unit_price is None:
                raise ValueError(f"Unknown food item: {food_name}")
            line_total = unit_price * Decimal(int(qty))
            total += line_total
            items_saved.append({"name": food_name, "quantity": int(qty), "total_price": float(line_total)})
        _mem_orders[next_id] = items_saved
        _mem_tracking[next_id] = "in progress"
        return next_id, float(round(total, 2))

    ensure_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Advisory transaction lock avoids order_id race conditions across concurrent requests
            cur.execute("SELECT pg_advisory_xact_lock(73912)")
            cur.execute(
                """
                SELECT GREATEST(
                    COALESCE((SELECT MAX(order_id) FROM orders), 0),
                    COALESCE((SELECT MAX(order_id) FROM order_tracking), 0)
                ) + 1
                """
            )
            next_order_id = int(cur.fetchone()[0])

            total_price = Decimal("0.00")
            for food_name, quantity in order.items():
                qty = int(quantity)
                if qty <= 0:
                    continue
                cur.execute(
                    "SELECT item_id, price FROM food_items WHERE LOWER(name) = LOWER(%s)",
                    (food_name,),
                )
                item_row = cur.fetchone()
                if not item_row:
                    raise ValueError(f"Unknown food item: {food_name}")
                item_id, unit_price = item_row
                line_total = Decimal(str(unit_price)) * Decimal(qty)
                total_price += line_total

                cur.execute(
                    """
                    INSERT INTO orders (order_id, item_id, quantity, total_price)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (next_order_id, item_id, qty, line_total),
                )

            cur.execute(
                "INSERT INTO order_tracking (order_id, status) VALUES (%s, %s)",
                (next_order_id, "in progress"),
            )
        conn.commit()
        return next_order_id, float(round(total_price, 2))


def get_order_status(order_id: int) -> dict[str, Any] | None:
    """Retrieve order tracking status and item summary for a given order_id."""
    if not is_postgres_configured():
        status = _mem_tracking.get(order_id)
        if not status:
            return None
        items = _mem_orders.get(order_id, [])
        total = round(sum(i["total_price"] for i in items), 2)
        return {
            "order_id": order_id,
            "status": status,
            "items": items,
            "total_price": total,
        }

    ensure_schema()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status FROM order_tracking WHERE order_id = %s",
                (order_id,),
            )
            track_row = cur.fetchone()
            if not track_row:
                return None

            cur.execute(
                """
                SELECT f.name, o.quantity, o.total_price
                FROM orders o
                JOIN food_items f ON o.item_id = f.item_id
                WHERE o.order_id = %s
                ORDER BY o.item_id
                """,
                (order_id,),
            )
            item_rows = cur.fetchall()
            items = [
                {
                    "name": r["name"],
                    "quantity": int(r["quantity"]),
                    "total_price": float(r["total_price"]),
                }
                for r in item_rows
            ]
            total = round(sum(i["total_price"] for i in items), 2)
            return {
                "order_id": order_id,
                "status": track_row["status"],
                "items": items,
                "total_price": total,
            }

"""Initialize and seed the Neon PostgreSQL database from database/schema_postgres.sql."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg2


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / ".env.local")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable is not set.", file=sys.stderr)
        print("Set it in .env or export DATABASE_URL='postgresql://...'", file=sys.stderr)
        sys.exit(1)

    schema_path = root_dir / "database" / "schema_postgres.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    print("Connecting to Neon PostgreSQL...")
    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute("SELECT COUNT(*) FROM food_items")
            item_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM order_tracking")
            order_count = cur.fetchone()[0]
        print(f"Database initialized successfully! ({item_count} menu items, {order_count} tracked orders)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

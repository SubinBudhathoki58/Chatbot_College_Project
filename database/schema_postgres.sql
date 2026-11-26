-- Taste of Himalaya Chatbot — PostgreSQL Schema for Neon
-- Safe to run multiple times (idempotent).

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

-- Seed menu items (Nepali cuisine)
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

-- Seed sample historical orders for testing "Track Order" (e.g., 40, 41, 42)
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

"""Creates and seeds `sample.db`, the database tool's store data (FR-30, NFR-10).

Architecture §5: 50 users, 30 products, 500 orders over the 12 months before
the seed date, and their order items.

- **Same input, same data:** the random generator always starts from seed 7,
  and every date is counted back from `seed_date`. Tests pass a fixed date,
  so a count like "orders in October" is known exactly. The app passes today.
- **Idempotent:** an existing `sample.db` is never touched, so the data
  doesn't change across restarts.
- The file is written under a temporary name first and renamed at the end,
  so a crash halfway never leaves a half-filled `sample.db` behind (which the
  "only if missing" rule would then keep forever).

Only the standard library is used: this file knows nothing about the app DB.
"""

import os
import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

SEED = 7
USER_COUNT = 50
ORDER_COUNT = 500

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    country TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total REAL NOT NULL
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
"""

# 30 products: (name, category, price). Fixed, so prices never depend on the seed.
PRODUCTS = [
    ("Laptop", "Electronics", 999.00),
    ("Smartphone", "Electronics", 699.00),
    ("Tablet", "Electronics", 399.00),
    ("Headphones", "Electronics", 149.00),
    ("Smartwatch", "Electronics", 249.00),
    ("Monitor", "Electronics", 229.00),
    ("Keyboard", "Electronics", 79.00),
    ("Mouse", "Electronics", 29.00),
    ("Desk Chair", "Furniture", 189.00),
    ("Standing Desk", "Furniture", 449.00),
    ("Bookshelf", "Furniture", 119.00),
    ("Desk Lamp", "Furniture", 39.00),
    ("Sofa", "Furniture", 899.00),
    ("Coffee Table", "Furniture", 159.00),
    ("Python Crash Course", "Books", 35.00),
    ("Clean Code", "Books", 42.00),
    ("The Pragmatic Programmer", "Books", 45.00),
    ("Design Patterns", "Books", 55.00),
    ("Cookbook", "Books", 25.00),
    ("Running Shoes", "Sports", 120.00),
    ("Yoga Mat", "Sports", 30.00),
    ("Dumbbell Set", "Sports", 85.00),
    ("Bicycle Helmet", "Sports", 60.00),
    ("Tennis Racket", "Sports", 140.00),
    ("Coffee Maker", "Kitchen", 89.00),
    ("Blender", "Kitchen", 65.00),
    ("Chef Knife", "Kitchen", 50.00),
    ("Frying Pan", "Kitchen", 40.00),
    ("Toaster", "Kitchen", 35.00),
    ("Water Bottle", "Kitchen", 15.00),
]

FIRST_NAMES = ["Alice", "Ben", "Chen", "Dana", "Eli", "Fatima", "George", "Hana",
               "Ivan", "Julia", "Kofi", "Lena", "Mateo", "Noa", "Omar", "Priya"]
LAST_NAMES = ["Smith", "Cohen", "Garcia", "Kim", "Müller", "Rossi", "Silva",
              "Tanaka", "Levi", "Novak", "Brown", "Dubois"]
COUNTRIES = ["USA", "UK", "Germany", "France", "Israel", "Japan", "Brazil", "India"]
STATUSES = ["completed", "shipped", "pending", "cancelled"]
STATUS_WEIGHTS = [70, 15, 10, 5]


def seed_if_missing(path: Path, seed_date: date) -> None:
    """Create and fill `path`, unless it already exists."""
    if path.exists():
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)  # left over from an earlier crash
    with closing(sqlite3.connect(tmp)) as conn:
        conn.executescript(SCHEMA)
        _fill(conn, seed_date)
        conn.commit()
    os.replace(tmp, path)  # the rename makes the finished file appear in one step


def _fill(conn: sqlite3.Connection, seed_date: date) -> None:
    rng = random.Random(SEED)

    conn.executemany(
        "INSERT INTO products (id, name, category, price) VALUES (?, ?, ?, ?)",
        [(i, *product) for i, product in enumerate(PRODUCTS, start=1)],
    )

    users = []
    for i in range(1, USER_COUNT + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        # Every user signed up 1-2 years before the seed date, so before all orders.
        created = seed_date - timedelta(days=rng.randint(366, 730))
        email = f"{first}.{last}{i}@example.com".lower()
        users.append((i, f"{first} {last}", email, rng.choice(COUNTRIES), created.isoformat()))
    conn.executemany(
        "INSERT INTO users (id, name, email, country, created_at) VALUES (?, ?, ?, ?, ?)", users
    )

    # Dates first, sorted, so order ids go up with the date like in a real shop.
    # 0..365 days back covers seed_date - 1 year .. seed_date (NFR-10).
    order_dates = sorted(seed_date - timedelta(days=rng.randint(0, 365)) for _ in range(ORDER_COUNT))
    orders, items = [], []
    for order_id, order_date in enumerate(order_dates, start=1):
        total = 0.0
        for _ in range(rng.randint(1, 4)):
            product_id = rng.randint(1, len(PRODUCTS))
            quantity = rng.randint(1, 3)
            unit_price = PRODUCTS[product_id - 1][2]
            items.append((order_id, product_id, quantity, unit_price))
            total += quantity * unit_price
        status = rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        orders.append(
            (order_id, rng.randint(1, USER_COUNT), order_date.isoformat(), status, round(total, 2))
        )
    conn.executemany(
        "INSERT INTO orders (id, user_id, order_date, status, total) VALUES (?, ?, ?, ?, ?)",
        orders,
    )
    conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        items,
    )

import sqlite3
import time

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    city TEXT,
    email TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    amount REAL,
    product TEXT,
    status TEXT CHECK(status IN ('pending','shipped','delivered','cancelled')),
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT,
    salary REAL,
    manager_id INTEGER REFERENCES employees(id)
);
"""

SEED_SQL = """
INSERT INTO customers VALUES
  (1,'Alice',34,'New York','alice@email.com'),
  (2,'Bob',28,'Chicago','bob@email.com'),
  (3,'Carol',45,'New York','carol@email.com'),
  (4,'Dan',31,'Houston','dan@email.com'),
  (5,'Eve',52,'Chicago','eve@email.com'),
  (6,'Frank',29,'Seattle','frank@email.com'),
  (7,'Grace',38,'Boston','grace@email.com'),
  (8,'Hank',41,'Denver','hank@email.com');

INSERT INTO orders VALUES
  (1,1,150.00,'Laptop','delivered','2024-01-15'),
  (2,1,25.00,'Book','delivered','2024-02-01'),
  (3,2,300.00,'Phone','delivered','2024-01-20'),
  (4,3,75.00,'Headphones','pending','2024-02-10'),
  (5,4,500.00,'Monitor','delivered','2024-01-05'),
  (6,5,45.00,'Keyboard','cancelled','2024-02-15'),
  (7,2,200.00,'Tablet','delivered','2024-01-25'),
  (8,3,90.00,'Mouse','shipped','2024-02-20'),
  (9,7,120.00,'Speaker','delivered','2024-03-01'),
  (10,8,350.00,'Camera','delivered','2024-03-05');

INSERT INTO employees VALUES
  (1,'Sarah','Engineering',85000,NULL),
  (2,'Tom','Engineering',72000,1),
  (3,'Lisa','Marketing',65000,NULL),
  (4,'Mark','Marketing',58000,3),
  (5,'Jane','Engineering',55000,1),
  (6,'Paul','HR',62000,NULL),
  (7,'Anna','HR',48000,6),
  (8,'Kevin','Marketing',70000,3),
  (9,'Raj','Engineering',92000,NULL),
  (10,'Mia','Finance',78000,NULL);
"""

SCHEMA_INFO = """Tables and columns:
- customers(id INTEGER, name TEXT, age INTEGER, city TEXT, email TEXT)
- orders(id INTEGER, customer_id INTEGER, amount REAL, product TEXT, status TEXT, created_at TEXT)
  status values: 'pending', 'shipped', 'delivered', 'cancelled'
- employees(id INTEGER, name TEXT, department TEXT, salary REAL, manager_id INTEGER)

Foreign keys:
- orders.customer_id -> customers.id
- employees.manager_id -> employees.id"""


def create_session_db() -> sqlite3.Connection:
    """Creates a fresh in-memory SQLite DB seeded with test data."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()
    return conn


def execute_query(conn: sqlite3.Connection, sql: str) -> dict:
    """Execute a SQL query and return structured result."""
    start = time.perf_counter()
    try:
        cursor = conn.execute(sql)
        rows = [list(r) for r in cursor.fetchall()]
        columns = [d[0] for d in cursor.description] if cursor.description else []
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "success": True,
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
            "error": None,
            "execution_time_ms": round(elapsed, 3),
        }
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "success": False,
            "rows": [],
            "columns": [],
            "row_count": 0,
            "error": str(e),
            "execution_time_ms": round(elapsed, 3),
        }

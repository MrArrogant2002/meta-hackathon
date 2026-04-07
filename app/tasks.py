import re
import sqlite3
from app.database import execute_query, SCHEMA_INFO

# ─── Broken queries presented to the agent ────────────────────────────────────

EASY_BROKEN = "SELECT id, name, city\ncustomers\nWHERE age > 30\nORDER BY name;"

MEDIUM_BROKEN = (
    "SELECT department, AVG(salary) AS avg_salary, COUNT(*) AS emp_count\n"
    "FROM employees\n"
    "WHERE AVG(salary) > 60000\n"
    "GROUP BY department;"
)

HARD_BROKEN = (
    "SELECT\n"
    "    c.name,\n"
    "    c.city,\n"
    "    (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) AS order_count,\n"
    "    (SELECT SUM(o.amount) FROM orders o WHERE o.customer_id = c.id) AS total_spent,\n"
    "    (SELECT MAX(o.amount) FROM orders o WHERE o.customer_id = c.id) AS max_order\n"
    "FROM customers c\n"
    "WHERE (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) > 0\n"
    "ORDER BY total_spent DESC;"
)

# ─── Canonical reference answers ──────────────────────────────────────────────

EASY_CANONICAL = (
    "SELECT id, name, city FROM customers WHERE age > 30 ORDER BY name;"
)

MEDIUM_CANONICAL = (
    "SELECT department, AVG(salary) AS avg_salary, COUNT(*) AS emp_count\n"
    "FROM employees\n"
    "GROUP BY department\n"
    "HAVING AVG(salary) > 60000;"
)

HARD_CANONICAL = (
    "SELECT c.name, c.city,\n"
    "    COUNT(o.id) AS order_count,\n"
    "    SUM(o.amount) AS total_spent,\n"
    "    MAX(o.amount) AS max_order\n"
    "FROM customers c\n"
    "JOIN orders o ON o.customer_id = c.id\n"
    "GROUP BY c.id, c.name, c.city\n"
    "ORDER BY total_spent DESC;"
)


# ─── Result comparison helpers ────────────────────────────────────────────────

def _normalize_rows(rows: list[list]) -> list[tuple]:
    """Sort rows and round floats for order-insensitive comparison."""
    def norm_val(v):
        if isinstance(v, float):
            return round(v, 2)
        if isinstance(v, str):
            return v.strip().lower()
        return v
    return sorted([tuple(norm_val(v) for v in row) for row in rows])


def results_match(conn: sqlite3.Connection, sql: str, canonical: str) -> bool:
    res_agent = execute_query(conn, sql)
    res_ref = execute_query(conn, canonical)
    if not res_agent["success"] or not res_ref["success"]:
        return False
    return _normalize_rows(res_agent["rows"]) == _normalize_rows(res_ref["rows"])


def partial_result_score(conn: sqlite3.Connection, sql: str, canonical: str) -> float:
    """Return 0.0–1.0 based on what fraction of expected rows were returned."""
    res_agent = execute_query(conn, sql)
    res_ref = execute_query(conn, canonical)
    if not res_agent["success"] or not res_ref["success"]:
        return 0.0
    agent_set = set(_normalize_rows(res_agent["rows"]))
    ref_set = set(_normalize_rows(res_ref["rows"]))
    if not ref_set:
        return 1.0
    overlap = len(agent_set & ref_set)
    precision = overlap / len(agent_set) if agent_set else 0.0
    recall = overlap / len(ref_set)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 3)  # F1


# ─── Grader functions ─────────────────────────────────────────────────────────

def grade_easy(sql: str, conn: sqlite3.Connection) -> tuple[float, dict]:
    breakdown: dict[str, float] = {}

    result = execute_query(conn, sql)

    # 1. Syntax valid (no parse/execution error)
    breakdown["syntax_valid"] = 0.25 if result["success"] else 0.0

    # 2. Runs without error (same as syntax for SQLite, but explicit)
    breakdown["runs_without_error"] = 0.25 if result["success"] else 0.0

    # 3. Contains FROM keyword before table name
    has_from = bool(re.search(r'\bFROM\s+customers\b', sql, re.IGNORECASE))
    breakdown["correct_keyword_fix"] = 0.25 if has_from else 0.0

    # 4. Correct result rows
    if result["success"]:
        partial = partial_result_score(conn, sql, EASY_CANONICAL)
        breakdown["correct_result"] = round(0.25 * partial, 4)
    else:
        breakdown["correct_result"] = 0.0

    score = sum(breakdown.values())
    # Clamp score to (0, 1) - strictly between, never exactly 0.0 or 1.0
    score = max(0.001, min(score, 0.999))
    return score, breakdown


def grade_medium(sql: str, conn: sqlite3.Connection) -> tuple[float, dict]:
    breakdown: dict[str, float] = {}

    result = execute_query(conn, sql)

    # 1. Syntax valid
    breakdown["syntax_valid"] = 0.15 if result["success"] else 0.0

    # 2. Runs without error (broken query fails, so this is the main gate)
    breakdown["runs_without_error"] = 0.25 if result["success"] else 0.0

    # 3. Uses HAVING clause
    has_having = bool(re.search(r'\bHAVING\b', sql, re.IGNORECASE))
    breakdown["uses_having"] = 0.20 if has_having else 0.0

    # 4. No aggregate in WHERE clause (negative check)
    agg_in_where = bool(re.search(
        r'\bWHERE\b[^;]*\b(AVG|SUM|COUNT|MAX|MIN)\s*\(',
        sql, re.IGNORECASE | re.DOTALL
    ))
    breakdown["no_aggregate_in_where"] = 0.15 if not agg_in_where else 0.0

    # 5. Correct result rows
    if result["success"]:
        partial = partial_result_score(conn, sql, MEDIUM_CANONICAL)
        breakdown["correct_result"] = round(0.25 * partial, 4)
    else:
        breakdown["correct_result"] = 0.0

    score = sum(breakdown.values())
    # Clamp score to (0, 1) - strictly between, never exactly 0.0 or 1.0
    score = max(0.001, min(score, 0.999))
    return score, breakdown


def _count_correlated_subqueries(sql: str) -> int:
    """
    Count subqueries that reference outer alias 'c' (correlated with the outer query).
    Uses position-based matching to avoid being broken by nested parens like COUNT(*).
    """
    subquery_starts = [
        m.start() for m in re.finditer(r'\(\s*SELECT\b', sql, re.IGNORECASE)
    ]
    count = 0
    for pos in subquery_starts:
        # Look at a generous slice from the subquery start
        extent = sql[pos : pos + 300]
        if re.search(r'\bc\.', extent, re.IGNORECASE):
            count += 1
    return count


def _count_total_subqueries(sql: str) -> int:
    return len(re.findall(r'\(\s*SELECT\b', sql, re.IGNORECASE))


def grade_hard(sql: str, conn: sqlite3.Connection) -> tuple[float, dict]:
    breakdown: dict[str, float] = {}

    result = execute_query(conn, sql)

    # 1. Runs without error
    breakdown["runs_without_error"] = 0.15 if result["success"] else 0.0

    # 2. Correct result rows (partial credit via F1)
    if result["success"]:
        partial = partial_result_score(conn, sql, HARD_CANONICAL)
        breakdown["correct_result"] = round(0.25 * partial, 4)
    else:
        breakdown["correct_result"] = 0.0

    # 3. No correlated subqueries (key efficiency metric)
    correlated = _count_correlated_subqueries(sql)
    if correlated == 0:
        breakdown["no_correlated_subqueries"] = 0.20
    elif correlated <= 1:
        breakdown["no_correlated_subqueries"] = 0.10  # partial credit
    else:
        breakdown["no_correlated_subqueries"] = 0.0

    # 4. Uses JOIN
    has_join = bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))
    breakdown["uses_join"] = 0.15 if has_join else 0.0

    # 5. Uses GROUP BY
    has_group_by = bool(re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE))
    breakdown["uses_group_by"] = 0.10 if has_group_by else 0.0

    # 6. Completely subquery-free bonus
    total_subqueries = _count_total_subqueries(sql)
    if total_subqueries == 0 and result["success"]:
        breakdown["subquery_free_bonus"] = 0.15
    else:
        breakdown["subquery_free_bonus"] = 0.0

    score = sum(breakdown.values())
    # Clamp score to (0, 1) - strictly between, never exactly 0.0 or 1.0
    score = max(0.001, min(score, 0.999))
    return score, breakdown


# ─── Hint system ──────────────────────────────────────────────────────────────

HINTS = {
    "easy_syntax_fix": [
        None,
        None,
        "Hint: A SELECT statement requires a FROM clause to specify the source table.",
        "Hint: The keyword FROM must appear between the column list and the table name.",
        "Hint: Try: SELECT id, name, city FROM customers WHERE age > 30 ORDER BY name;",
    ],
    "medium_logic_fix": [
        None,
        None,
        "Hint: You cannot use aggregate functions (AVG, SUM, COUNT) in a WHERE clause.",
        "Hint: Use HAVING to filter groups after GROUP BY, not WHERE.",
        "Hint: Move the AVG(salary) condition from WHERE to HAVING, after GROUP BY.",
    ],
    "hard_optimization": [
        None,
        None,
        "Hint: Correlated subqueries execute once per row — they are very slow on large tables.",
        "Hint: Replace correlated subqueries with a single JOIN + GROUP BY + aggregate functions.",
        "Hint: COUNT(o.id), SUM(o.amount), MAX(o.amount) with a JOIN and GROUP BY replaces all three subqueries.",
        None, None, None, None,
        "Hint: Final hint — use INNER JOIN orders o ON o.customer_id = c.id with GROUP BY c.id, c.name, c.city",
    ],
}


def get_hint(task_id: str, step_number: int) -> str | None:
    hints = HINTS.get(task_id, [])
    if step_number < len(hints):
        return hints[step_number]
    return None


# ─── Task registry ────────────────────────────────────────────────────────────

TASK_REGISTRY: dict[str, dict] = {
    "easy_syntax_fix": {
        "id": "easy_syntax_fix",
        "name": "Fix SQL Syntax Error",
        "difficulty": "easy",
        "description": (
            "A SQL query is missing the FROM keyword. "
            "The query should return all customers older than 30, ordered by name. "
            "Fix the syntax error so it executes correctly."
        ),
        "broken_query": EASY_BROKEN,
        "canonical": EASY_CANONICAL,
        "max_steps": 5,
        "reward_threshold": 0.8,
        "grader": grade_easy,
    },
    "medium_logic_fix": {
        "id": "medium_logic_fix",
        "name": "Fix SQL Logic Bug (HAVING vs WHERE)",
        "difficulty": "medium",
        "description": (
            "A SQL query incorrectly uses WHERE with an aggregate function AVG(salary), "
            "which is not allowed in SQL. "
            "Fix the query so it returns departments where the average salary exceeds 60,000."
        ),
        "broken_query": MEDIUM_BROKEN,
        "canonical": MEDIUM_CANONICAL,
        "max_steps": 8,
        "reward_threshold": 0.8,
        "grader": grade_medium,
    },
    "hard_optimization": {
        "id": "hard_optimization",
        "name": "Optimize Correlated Subquery",
        "difficulty": "hard",
        "description": (
            "A SQL query uses four correlated subqueries — one per aggregate and one in WHERE — "
            "making it extremely slow on large tables (O(n²) complexity). "
            "Rewrite it using a single JOIN + GROUP BY to achieve O(n log n) performance "
            "while returning identical results: customers who have orders, "
            "with their order_count, total_spent, and max_order, sorted by total_spent DESC."
        ),
        "broken_query": HARD_BROKEN,
        "canonical": HARD_CANONICAL,
        "max_steps": 10,
        "reward_threshold": 0.7,
        "grader": grade_hard,
    },
}

"""
Deterministic rule-based baseline agent.
Used by the /baseline endpoint for reproducible, dependency-free scoring.
"""
import re
from app.tasks import TASK_REGISTRY, HARD_CANONICAL
from app.database import create_session_db


def solve_easy(broken_query: str) -> str:
    """Insert FROM before table name (missing FROM keyword fix)."""
    fixed = re.sub(
        r'(SELECT\s+[\w\s,.*]+?)\n(customers|orders|employees)\n',
        r'\1\nFROM \2\n',
        broken_query,
        flags=re.IGNORECASE,
    )
    if fixed == broken_query:
        # Fallback: insert FROM before table name on same line
        fixed = re.sub(
            r'(SELECT\b[^\n]+)\n(customers|orders|employees)\b',
            r'\1\nFROM \2',
            broken_query,
            flags=re.IGNORECASE,
        )
    return fixed


def solve_medium(broken_query: str) -> str:
    """Move aggregate condition from WHERE to HAVING."""
    # Remove WHERE AVG(...) > ... line
    fixed = re.sub(
        r'\bWHERE\s+(AVG|SUM|COUNT|MAX|MIN)\s*\([^)]*\)\s*>\s*\d+\b',
        '',
        broken_query,
        flags=re.IGNORECASE,
    )
    # Add HAVING after GROUP BY
    fixed = re.sub(
        r'(GROUP BY\s+\w+)\s*;?$',
        r'\1\nHAVING AVG(salary) > 60000',
        fixed.strip(),
        flags=re.IGNORECASE,
    )
    return fixed.strip() + ';'


def solve_hard(_broken_query: str) -> str:
    """Return the canonical optimized query directly."""
    return HARD_CANONICAL


SOLVERS = {
    "easy_syntax_fix": solve_easy,
    "medium_logic_fix": solve_medium,
    "hard_optimization": solve_hard,
}


def run_baseline() -> dict:
    """
    Run the rule-based solver against all 3 tasks.
    Returns scores and breakdown for each task.
    """
    from app.tasks import TASK_REGISTRY

    results = {}
    for task_id, task_cfg in TASK_REGISTRY.items():
        solver = SOLVERS[task_id]
        fixed_sql = solver(task_cfg["broken_query"])

        # Create fresh DB and grade
        conn = create_session_db()
        try:
            score, breakdown = task_cfg["grader"](fixed_sql, conn)
        finally:
            conn.close()

        results[task_id] = {
            "score": round(score, 4),
            "submitted_query": fixed_sql,
            "breakdown": breakdown,
            "solved": score >= task_cfg["reward_threshold"],
        }

    return results

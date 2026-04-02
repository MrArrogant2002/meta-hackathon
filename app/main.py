import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Optional

from app.models import (
    Action, ResetRequest, ResetResponse, StepResponse,
    StateResponse, GraderRequest, GraderResponse,
    TaskInfo, BaselineResult,
)
from app.tasks import TASK_REGISTRY
from app.session_store import store
import app.environment as env


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background task: clean up expired sessions every 5 minutes
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            store.cleanup_expired()

    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="SQL Query Debugging & Optimization Environment",
    description=(
        "An OpenEnv-compliant environment where AI agents learn to debug and optimize SQL queries. "
        "Three tasks (easy → medium → hard) covering syntax fixes, logic bugs, and query optimization."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Health / Root ────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {
        "name": "sql-query-debugging",
        "version": "1.0.0",
        "status": "ok",
        "tasks": list(TASK_REGISTRY.keys()),
        "active_sessions": store.active_count(),
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "active_sessions": store.active_count()}


# ─── OpenEnv Core Endpoints ───────────────────────────────────────────────────

@app.post("/reset", response_model=ResetResponse, tags=["openenv"])
def reset(req: Optional[ResetRequest] = None):
    """Reset the environment for a given task. Returns initial observation and session_id."""
    try:
        return env.reset(req or ResetRequest())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/step", response_model=StepResponse, tags=["openenv"])
def step(
    action: Action,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    session_id: Optional[str] = None,
):
    """Submit a SQL query as an action. Pass session_id via X-Session-Id header or query param."""
    sid = x_session_id or session_id
    if not sid:
        raise HTTPException(
            status_code=422,
            detail="session_id required — pass via X-Session-Id header or ?session_id= query param",
        )
    try:
        return env.step(sid, action)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/state", response_model=StateResponse, tags=["openenv"])
def state(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    session_id: Optional[str] = None,
):
    """Return full current state including trajectory history."""
    sid = x_session_id or session_id
    if not sid:
        raise HTTPException(status_code=422, detail="session_id required")
    try:
        return env.get_state(sid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Required Additional Endpoints ────────────────────────────────────────────

@app.get("/tasks", response_model=list[TaskInfo], tags=["openenv"])
def list_tasks():
    """Return all tasks with their action schema and metadata."""
    action_schema = {
        "type": "object",
        "required": ["sql_query"],
        "properties": {
            "sql_query": {
                "type": "string",
                "description": "The SQL query to submit as an attempt",
            },
            "explanation": {
                "type": "string",
                "description": "Agent's optional explanation of the change",
            },
        },
    }
    return [
        TaskInfo(
            id=cfg["id"],
            name=cfg["name"],
            difficulty=cfg["difficulty"],
            description=cfg["description"],
            max_steps=cfg["max_steps"],
            reward_threshold=cfg["reward_threshold"],
            action_schema=action_schema,
        )
        for cfg in TASK_REGISTRY.values()
    ]


@app.post("/grader", response_model=GraderResponse, tags=["openenv"])
def grader(req: GraderRequest):
    """Return the grader score for a completed (or in-progress) episode."""
    try:
        return env.get_grader_score(req.session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/baseline", response_model=BaselineResult, tags=["openenv"])
def run_baseline():
    """
    Run the deterministic rule-based baseline agent on all 3 tasks.
    Returns reproducible scores without requiring any external API.
    """
    from baseline.rule_based import run_baseline as _run
    results = _run()

    scores = {task_id: r["score"] for task_id, r in results.items()}
    details = {
        task_id: {
            "score": r["score"],
            "solved": r["solved"],
            "breakdown": r["breakdown"],
            "submitted_query": r["submitted_query"],
        }
        for task_id, r in results.items()
    }

    return BaselineResult(
        method="rule_based",
        model="deterministic",
        scores=scores,
        details=details,
        reproducible=True,
    )

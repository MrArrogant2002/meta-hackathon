import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException

import app.environment as env
from app.models import (
    Action,
    BaselineResult,
    GraderRequest,
    GraderResponse,
    ResetRequest,
    ResetResponse,
    StateResponse,
    StepResponse,
    TaskInfo,
)
from app.session_store import store
from app.tasks import TASK_REGISTRY


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    title="Customer Support Escalation Desk",
    description=(
        "An OpenEnv-compliant environment for real-world customer support decisions: refund, request_info, "
        "troubleshoot, escalate, or close."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", tags=["health"])
def root():
    return {
        "name": "customer-support-escalation-desk",
        "version": "1.0.0",
        "status": "ok",
        "tasks": list(TASK_REGISTRY.keys()),
        "active_sessions": store.active_count(),
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "active_sessions": store.active_count()}


@app.post("/reset", response_model=ResetResponse, tags=["openenv"])
def reset(req: Optional[ResetRequest] = None):
    try:
        return env.reset(req or ResetRequest())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/step", response_model=StepResponse, tags=["openenv"])
def step(
    action: Action,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    session_id: Optional[str] = None,
):
    sid = x_session_id or session_id
    if not sid:
        raise HTTPException(
            status_code=422,
            detail="session_id required — pass via X-Session-Id header or ?session_id= query param",
        )
    try:
        return env.step(sid, action)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/state", response_model=StateResponse, tags=["openenv"])
def state(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    session_id: Optional[str] = None,
):
    sid = x_session_id or session_id
    if not sid:
        raise HTTPException(status_code=422, detail="session_id required")
    try:
        return env.get_state(sid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _action_schema() -> dict:
    return {
        "type": "object",
        "required": ["decision", "priority"],
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["refund", "troubleshoot", "escalate", "close", "request_info"],
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
            },
            "reason_codes": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "damaged_item",
                        "technical_issue",
                        "missing_information",
                        "within_return_window",
                        "policy_exception",
                        "fraud_risk",
                        "repeat_contact",
                    ],
                },
            },
            "request_fields": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "order_id",
                        "device_model",
                        "photo_evidence",
                        "delivery_date",
                        "serial_number",
                    ],
                },
            },
            "recommended_steps": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "confirm_power_source",
                        "factory_reset",
                        "check_tracking",
                        "verify_account_email",
                    ],
                },
            },
            "escalation_team": {
                "type": "string",
                "enum": [
                    "none",
                    "billing_review",
                    "logistics_ops",
                    "technical_support",
                    "fraud_review",
                    "retention_desk",
                ],
            },
            "customer_message": {"type": "string"},
        },
    }


@app.get("/tasks", response_model=list[TaskInfo], tags=["openenv"])
def list_tasks():
    schema = _action_schema()
    return [
        TaskInfo(
            id=cfg["id"],
            name=cfg["name"],
            difficulty=cfg["difficulty"],
            description=cfg["description"],
            max_steps=cfg["max_steps"],
            reward_threshold=cfg["reward_threshold"],
            action_schema=schema,
        )
        for cfg in TASK_REGISTRY.values()
    ]


@app.post("/grader", response_model=GraderResponse, tags=["openenv"])
def grader(req: GraderRequest):
    try:
        return env.get_grader_score(req.session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/baseline", response_model=BaselineResult, tags=["openenv"])
def run_baseline():
    from baseline.rule_based import run_baseline as _run

    results = _run()
    scores = {task_id: item["score"] for task_id, item in results.items()}
    details = {
        task_id: {
            "score": item["score"],
            "solved": item["solved"],
            "breakdown": item["breakdown"],
            "actions": item["actions"],
        }
        for task_id, item in results.items()
    }
    return BaselineResult(
        method="rule_based",
        model="deterministic_support_policy_agent",
        scores=scores,
        details=details,
        reproducible=True,
    )


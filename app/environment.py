from app.models import (
    Action, Observation, Reward, StepResponse,
    ResetRequest, ResetResponse, ExecutionResult,
)
from app.tasks import TASK_REGISTRY, get_hint
from app.database import execute_query, SCHEMA_INFO
from app.session_store import store, Session


def _build_observation(session: Session, task_cfg: dict, error_msg: str | None = None,
                        last_sql: str | None = None, exec_result: dict | None = None) -> Observation:
    hint = get_hint(session.task_id, session.step_number)

    exec_model = None
    if exec_result is not None:
        exec_model = ExecutionResult(
            success=exec_result["success"],
            rows=exec_result["rows"],
            columns=exec_result["columns"],
            row_count=exec_result["row_count"],
            error=exec_result["error"],
            execution_time_ms=exec_result["execution_time_ms"],
        )

    return Observation(
        task_id=session.task_id,
        task_description=task_cfg["description"],
        broken_query=task_cfg["broken_query"],
        schema_info=SCHEMA_INFO,
        error_message=error_msg,
        last_submission=last_sql,
        last_execution_result=exec_model,
        hint=hint,
        step_number=session.step_number,
        max_steps=task_cfg["max_steps"],
        done=session.done,
    )


def reset(req: ResetRequest) -> ResetResponse:
    task_id = req.task_id
    if task_id not in TASK_REGISTRY:
        raise ValueError(f"Unknown task_id '{task_id}'. Valid: {list(TASK_REGISTRY.keys())}")

    session = store.create(task_id=task_id, session_id=req.session_id)
    task_cfg = TASK_REGISTRY[task_id]
    obs = _build_observation(session, task_cfg)
    return ResetResponse(session_id=session.session_id, observation=obs)


def step(session_id: str, action: Action) -> StepResponse:
    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found. Call /reset first.")

    task_cfg = TASK_REGISTRY[session.task_id]

    if session.done:
        # Episode already finished — return last observation with zero reward
        obs = _build_observation(session, task_cfg)
        return StepResponse(
            observation=obs,
            reward=Reward(value=0.0, components={}, reason="Episode already done."),
            done=True,
            info={"warning": "Episode is already done. Call /reset to start a new episode."},
        )

    sql = action.sql_query.strip()
    exec_result = execute_query(session.db_conn, sql)

    # Run grader
    grader_fn = task_cfg["grader"]
    score, breakdown = grader_fn(sql, session.db_conn)

    # Delta reward: improvement over previous best
    delta = max(0.0, score - session.best_score)
    # Small penalty for regression (submitting worse query)
    if score < session.best_score - 0.05:
        delta = -0.05

    session.best_score = max(session.best_score, score)
    session.cumulative_reward += delta
    session.step_number += 1

    # Check episode termination
    threshold = task_cfg["reward_threshold"]
    timeout = session.step_number >= task_cfg["max_steps"]
    solved = session.best_score >= threshold
    session.done = solved or timeout

    # Efficiency bonus (end of episode, only if solved)
    efficiency_bonus = 0.0
    if solved:
        efficiency_bonus = round(
            (task_cfg["max_steps"] - session.step_number) / task_cfg["max_steps"] * 0.2, 4
        )

    # Build reward
    reward_value = round(min(delta + efficiency_bonus, 1.0), 4)
    reason_parts = []
    if score > 0:
        reason_parts.append(f"grader_score={score:.3f}")
    if not exec_result["success"]:
        reason_parts.append(f"error={exec_result['error']}")
    if solved:
        reason_parts.append("SOLVED")
    if timeout and not solved:
        reason_parts.append("TIMEOUT")

    reward = Reward(
        value=reward_value,
        components=breakdown,
        reason="; ".join(reason_parts) if reason_parts else "no progress",
    )

    # Record history
    session.history.append({
        "step": session.step_number,
        "sql": sql,
        "score": score,
        "reward": reward_value,
        "breakdown": breakdown,
    })

    obs = _build_observation(
        session, task_cfg,
        error_msg=exec_result["error"] if not exec_result["success"] else None,
        last_sql=sql,
        exec_result=exec_result,
    )

    info = {
        "task_id": session.task_id,
        "step_number": session.step_number,
        "grader_score": score,
        "best_score_so_far": session.best_score,
        "grader_breakdown": breakdown,
        "solved": solved,
        "timeout": timeout and not solved,
        "efficiency_bonus": efficiency_bonus,
    }

    return StepResponse(observation=obs, reward=reward, done=session.done, info=info)


def get_state(session_id: str):
    from app.models import StateResponse
    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found.")
    return StateResponse(
        session_id=session_id,
        task_id=session.task_id,
        step_number=session.step_number,
        done=session.done,
        cumulative_reward=round(session.cumulative_reward, 4),
        best_score=round(session.best_score, 4),
        history=session.history,
    )


def get_grader_score(session_id: str):
    from app.models import GraderResponse
    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found.")

    task_cfg = TASK_REGISTRY[session.task_id]
    # Use best submission from history if available
    if session.history:
        best_entry = max(session.history, key=lambda h: h["score"])
        score = best_entry["score"]
        breakdown = best_entry["breakdown"]
    else:
        score = 0.001  # Must be > 0.0 for Phase 2 validation
        breakdown = {}

    return GraderResponse(
        session_id=session_id,
        task_id=session.task_id,
        final_score=round(score, 4),
        breakdown=breakdown,
        solved=score >= task_cfg["reward_threshold"],
        done=session.done,
    )

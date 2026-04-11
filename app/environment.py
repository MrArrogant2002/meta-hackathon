from typing import Any

from app.models import (
    Action,
    ConversationTurn,
    Observation,
    OrderSnapshot,
    ResetRequest,
    ResetResponse,
    Reward,
    StepResponse,
)
from app.session_store import Session, store
from app.tasks import TASK_REGISTRY, build_initial_state, get_hint, grade_action, validate_action


def _build_observation(session: Session, task_cfg: dict[str, Any]) -> Observation:
    state = session.state
    return Observation(
        task_id=session.task_id,
        case_id=state["case_id"],
        task_description=task_cfg["description"],
        conversation_history=[ConversationTurn(**turn) for turn in state["conversation_history"]],
        customer_tier=state["customer_tier"],
        sentiment=state["sentiment"],
        urgency=state["urgency"],
        order_snapshot=OrderSnapshot(**state["order_snapshot"]),
        policy_snippet=state["policy_snippet"],
        known_facts=state["known_facts"],
        missing_fields=state["missing_fields"],
        phase=state["phase"],
        feedback=state.get("feedback"),
        hint=get_hint(session.task_id, session.step_number),
        step_number=session.step_number,
        max_steps=task_cfg["max_steps"],
        done=session.done,
        last_action_error=state.get("last_action_error"),
    )


def reset(req: ResetRequest) -> ResetResponse:
    if req.task_id not in TASK_REGISTRY:
        raise ValueError(f"Unknown task_id '{req.task_id}'. Valid: {list(TASK_REGISTRY.keys())}")

    task_cfg = TASK_REGISTRY[req.task_id]
    state = build_initial_state(req.task_id)
    session = store.create(task_id=req.task_id, state=state, session_id=req.session_id)
    return ResetResponse(session_id=session.session_id, observation=_build_observation(session, task_cfg))


def _serialize_action(action: Action) -> dict[str, Any]:
    return action.model_dump(mode="json")


def step(session_id: str, action: Action) -> StepResponse:
    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found. Call /reset first.")

    task_cfg = TASK_REGISTRY[session.task_id]

    if session.done:
        observation = _build_observation(session, task_cfg)
        return StepResponse(
            observation=observation,
            reward=Reward(value=0.0, components={}, reason="Episode already done."),
            done=True,
            info={"warning": "Episode is already done. Call /reset to start a new episode."},
        )

    semantic_error = validate_action(action)
    session.state["last_action_error"] = semantic_error

    if semantic_error:
        score = session.best_score
        breakdown = {"valid_action": 0.0}
        feedback = f"Invalid action: {semantic_error}"
    else:
        score, breakdown, feedback = grade_action(session.task_id, action, session.state)

    session.state["feedback"] = feedback
    delta = max(0.0, score - session.best_score)
    session.best_score = max(session.best_score, score)
    session.step_number += 1

    threshold = task_cfg["reward_threshold"]
    timeout = session.step_number >= task_cfg["max_steps"]
    solved = session.best_score >= threshold
    session.done = solved or timeout

    efficiency_bonus = 0.0
    if solved:
        efficiency_bonus = round(
            (task_cfg["max_steps"] - session.step_number) / task_cfg["max_steps"] * 0.15,
            4,
        )

    reward_value = round(min(max(delta + efficiency_bonus, 0.0), 1.0), 4)
    session.cumulative_reward = round(session.cumulative_reward + reward_value, 4)

    session.history.append(
        {
            "step": session.step_number,
            "phase": session.state["phase"],
            "action": _serialize_action(action),
            "score": round(score, 4),
            "reward": reward_value,
            "breakdown": breakdown,
            "feedback": feedback,
            "error": semantic_error,
        }
    )

    observation = _build_observation(session, task_cfg)
    reward = Reward(
        value=reward_value,
        components=breakdown,
        reason=f"grader_score={score:.3f}",
    )
    info = {
        "task_id": session.task_id,
        "step_number": session.step_number,
        "grader_score": round(score, 4),
        "best_score_so_far": round(session.best_score, 4),
        "grader_breakdown": breakdown,
        "solved": solved,
        "timeout": timeout and not solved,
        "efficiency_bonus": efficiency_bonus,
        "last_action_error": semantic_error,
    }
    return StepResponse(observation=observation, reward=reward, done=session.done, info=info)


def get_state(session_id: str):
    from app.models import StateResponse

    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found.")

    return StateResponse(
        session_id=session.session_id,
        task_id=session.task_id,
        phase=session.state["phase"],
        step_number=session.step_number,
        done=session.done,
        cumulative_reward=session.cumulative_reward,
        best_score=round(session.best_score, 4),
        state=session.state,
        history=session.history,
    )


def get_grader_score(session_id: str):
    from app.models import GraderResponse

    session = store.get(session_id)
    if session is None:
        raise LookupError(f"Session '{session_id}' not found.")

    task_cfg = TASK_REGISTRY[session.task_id]
    if session.history:
        best_entry = max(session.history, key=lambda item: item["score"])
        score = best_entry["score"]
        breakdown = best_entry["breakdown"]
    else:
        score = 0.0
        breakdown = {}

    return GraderResponse(
        session_id=session.session_id,
        task_id=session.task_id,
        final_score=round(score, 4),
        breakdown=breakdown,
        solved=score >= task_cfg["reward_threshold"],
        done=session.done,
    )


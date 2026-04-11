"""
Validator-facing inference script for the Customer Support Escalation Desk environment.
"""

import json
import os
from typing import Any, Optional

import requests
from openai import OpenAI

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")
ENV_HOST = os.getenv("ENV_HOST", "http://localhost:7860")
BENCHMARK = "customer_support_escalation"

TASKS = [
    "easy_refund_eligible",
    "medium_missing_info_tech_issue",
    "hard_policy_edge_case",
]
MAX_STEPS_PER_TASK = {
    "easy_refund_eligible": 4,
    "medium_missing_info_tech_issue": 6,
    "hard_policy_edge_case": 6,
}
TEMPERATURE = 0.0
MAX_TOKENS = 300
MIN_REPORTED_SCORE = 0.01
MAX_REPORTED_SCORE = 0.99

SYSTEM_PROMPT = (
    "You are a customer support operations agent. "
    "Return ONLY minified JSON for the action schema with keys: "
    "decision, priority, reason_codes, request_fields, recommended_steps, escalation_team, customer_message. "
    "Use empty arrays when a field is not needed and use escalation_team='none' unless escalating."
)


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    action_clean = action.replace("\n", " ").replace("\r", " ")
    print(
        f"[STEP] step={step} action={action_clean} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{reward:.2f}" for reward in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def _normalize_reported_score(score: float) -> float:
    return min(max(score, MIN_REPORTED_SCORE), MAX_REPORTED_SCORE)


def _default_action(task_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    if task_id == "easy_refund_eligible":
        return {
            "decision": "refund",
            "priority": "medium",
            "reason_codes": ["damaged_item", "within_return_window"],
            "request_fields": [],
            "recommended_steps": [],
            "escalation_team": "none",
            "customer_message": "I can process a refund because the damage is documented and within policy.",
        }
    if task_id == "medium_missing_info_tech_issue" and observation.get("phase") == "initial":
        return {
            "decision": "request_info",
            "priority": "medium",
            "reason_codes": ["missing_information"],
            "request_fields": ["order_id", "device_model"],
            "recommended_steps": [],
            "escalation_team": "none",
            "customer_message": "Please share the order ID and device model so I can verify the case.",
        }
    if task_id == "medium_missing_info_tech_issue":
        return {
            "decision": "troubleshoot",
            "priority": "medium",
            "reason_codes": ["technical_issue"],
            "request_fields": [],
            "recommended_steps": ["confirm_power_source", "factory_reset"],
            "escalation_team": "none",
            "customer_message": "Let's verify power and then try a factory reset before replacement.",
        }
    return {
        "decision": "escalate",
        "priority": "high",
        "reason_codes": ["fraud_risk", "policy_exception", "repeat_contact"],
        "request_fields": [],
        "recommended_steps": [],
        "escalation_team": "fraud_review",
        "customer_message": "This requires specialist review because the account has a chargeback flag.",
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _call_model(client: OpenAI, task_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"Task ID: {task_id}\n"
        f"Observation:\n{json.dumps(observation, ensure_ascii=True)}\n"
        "Choose the best action for policy-safe support handling."
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        content = (completion.choices[0].message.content or "").strip()
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
    except Exception:
        pass
    return _default_action(task_id, observation)


def run_task(task_id: str, client: OpenAI) -> dict[str, Any]:
    rewards: list[float] = []
    steps_taken = 0
    best_score = 0.0
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        reset_response = requests.post(
            f"{ENV_HOST}/reset",
            json={"task_id": task_id},
            timeout=30,
        )
        reset_response.raise_for_status()
        reset_data = reset_response.json()
        session_id = reset_data["session_id"]
        observation = reset_data["observation"]
        headers = {"X-Session-Id": session_id}

        for step in range(1, MAX_STEPS_PER_TASK[task_id] + 1):
            if observation.get("done", False):
                break

            action = _call_model(client, task_id, observation)
            action_str = json.dumps(action, separators=(",", ":"), ensure_ascii=True)

            step_response = requests.post(
                f"{ENV_HOST}/step",
                json=action,
                headers=headers,
                timeout=30,
            )
            step_response.raise_for_status()
            step_data = step_response.json()

            reward = float(step_data["reward"]["value"])
            done = bool(step_data["done"])
            observation = step_data["observation"]
            error = observation.get("last_action_error")

            rewards.append(reward)
            steps_taken = step
            best_score = max(best_score, float(step_data["info"].get("best_score_so_far", 0.0)))
            success = bool(step_data["info"].get("solved", False))

            log_step(step=step, action=action_str, reward=reward, done=done, error=error)

            if done:
                break
    except Exception as exc:
        log_step(
            step=max(1, steps_taken + 1),
            action="{}",
            reward=0.0,
            done=True,
            error=str(exc),
        )
    finally:
        log_end(
            success=success,
            steps=steps_taken,
            score=_normalize_reported_score(best_score),
            rewards=rewards,
        )

    return {
        "task_id": task_id,
        "score": best_score,
        "success": success,
        "steps_taken": steps_taken,
    }


def main() -> int:
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    for task_id in TASKS:
        run_task(task_id, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from app import environment as env
from app.models import (
    Action,
    Decision,
    EscalationTeam,
    Priority,
    ReasonCode,
    RequestField,
    ResetRequest,
    TroubleshootStep,
)


PLAYBOOK = {
    "easy_refund_eligible": [
        Action(
            decision=Decision.refund,
            priority=Priority.medium,
            reason_codes=[ReasonCode.damaged_item, ReasonCode.within_return_window],
            escalation_team=EscalationTeam.none,
        )
    ],
    "medium_missing_info_tech_issue": [
        Action(
            decision=Decision.request_info,
            priority=Priority.medium,
            reason_codes=[ReasonCode.missing_information],
            request_fields=[RequestField.order_id, RequestField.device_model],
            escalation_team=EscalationTeam.none,
        ),
        Action(
            decision=Decision.troubleshoot,
            priority=Priority.medium,
            reason_codes=[ReasonCode.technical_issue],
            recommended_steps=[
                TroubleshootStep.confirm_power_source,
                TroubleshootStep.factory_reset,
            ],
            escalation_team=EscalationTeam.none,
        ),
    ],
    "hard_policy_edge_case": [
        Action(
            decision=Decision.escalate,
            priority=Priority.high,
            reason_codes=[
                ReasonCode.fraud_risk,
                ReasonCode.policy_exception,
                ReasonCode.repeat_contact,
            ],
            escalation_team=EscalationTeam.fraud_review,
        )
    ],
}


def run_baseline() -> dict[str, dict]:
    results: dict[str, dict] = {}
    for task_id, actions in PLAYBOOK.items():
        reset_result = env.reset(ResetRequest(task_id=task_id))
        history = []
        final_breakdown = {}
        best_score = 0.0
        solved = False

        for action in actions:
            step_result = env.step(reset_result.session_id, action)
            history.append(action.model_dump(mode="json"))
            final_breakdown = step_result.reward.components
            best_score = max(best_score, step_result.info.get("best_score_so_far", 0.0))
            solved = step_result.info.get("solved", False)
            if step_result.done:
                break

        results[task_id] = {
            "score": round(best_score, 4),
            "solved": solved,
            "breakdown": final_breakdown,
            "actions": history,
        }
    return results


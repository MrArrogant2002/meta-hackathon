from copy import deepcopy
from typing import Any

from app.models import (
    Action,
    Decision,
    EscalationTeam,
    Priority,
    ReasonCode,
    RequestField,
    TroubleshootStep,
)

TASK_IDS = [
    "easy_refund_eligible",
    "medium_missing_info_tech_issue",
    "hard_policy_edge_case",
]
MIN_TASK_SCORE = 0.01
MAX_TASK_SCORE = 0.99


def _serialize_enum_list(values: list) -> set[str]:
    return {value.value if hasattr(value, "value") else str(value) for value in values}


def _normalize_task_score(score: float) -> float:
    return round(min(max(score, MIN_TASK_SCORE), MAX_TASK_SCORE), 4)


def validate_action(action: Action) -> str | None:
    if action.decision == Decision.escalate and action.escalation_team == EscalationTeam.none:
        return "escalation_team must be set when decision=escalate"
    if action.decision != Decision.escalate and action.escalation_team != EscalationTeam.none:
        return "escalation_team must be 'none' unless decision=escalate"
    if action.decision == Decision.request_info and not action.request_fields:
        return "request_fields required when decision=request_info"
    return None


def _easy_state() -> dict[str, Any]:
    return {
        "case_id": "CASE-REFUND-101",
        "conversation_history": [
            {
                "speaker": "customer",
                "text": "My coffee grinder arrived with a cracked hopper. I uploaded photos and need a refund.",
            }
        ],
        "customer_tier": "standard",
        "sentiment": "frustrated",
        "urgency": "medium",
        "order_snapshot": {
            "order_id": "ORD-1042",
            "product_name": "BrewMaster Coffee Grinder",
            "days_since_purchase": 5,
            "days_since_delivery": 3,
            "replacement_active": False,
            "chargeback_flag": False,
            "photo_evidence_provided": True,
            "prior_refund": False,
        },
        "policy_snippet": (
            "Damaged item claims within 30 days of delivery with photo evidence may be refunded directly. "
            "No escalation is required unless fraud or prior refund abuse is detected."
        ),
        "known_facts": [
            "Customer included photo evidence.",
            "Item arrived damaged.",
            "The order is within the 30-day refund window.",
        ],
        "missing_fields": [],
        "phase": "initial",
        "feedback": None,
        "last_action_error": None,
    }


def _medium_state() -> dict[str, Any]:
    return {
        "case_id": "CASE-TECH-204",
        "conversation_history": [
            {
                "speaker": "customer",
                "text": "My blender stopped turning on after a week. Can you replace it?",
            }
        ],
        "customer_tier": "gold",
        "sentiment": "frustrated",
        "urgency": "medium",
        "order_snapshot": {
            "order_id": None,
            "product_name": None,
            "days_since_purchase": None,
            "days_since_delivery": None,
            "replacement_active": False,
            "chargeback_flag": False,
            "photo_evidence_provided": False,
            "prior_refund": False,
        },
        "policy_snippet": (
            "Technical issues require identity and order verification first. "
            "If key order details are missing, request them before refunding or escalating. "
            "Verified technical cases should go through first-line troubleshooting before replacement."
        ),
        "known_facts": [
            "The product reportedly does not power on.",
            "No verified order details are available yet.",
        ],
        "missing_fields": ["order_id", "device_model"],
        "phase": "initial",
        "phase1_score_raw": 0.0,
        "phase1_breakdown_raw": {},
        "feedback": None,
        "last_action_error": None,
    }


def _hard_state() -> dict[str, Any]:
    return {
        "case_id": "CASE-EDGE-309",
        "conversation_history": [
            {
                "speaker": "customer",
                "text": (
                    "I am a platinum customer and this is my third contact. Your agent promised an exception refund, "
                    "but I still have no working replacement. Fix this now."
                ),
            }
        ],
        "customer_tier": "platinum",
        "sentiment": "angry",
        "urgency": "high",
        "order_snapshot": {
            "order_id": "ORD-7781",
            "product_name": "SmartHome Air Purifier",
            "days_since_purchase": 46,
            "days_since_delivery": 40,
            "replacement_active": True,
            "chargeback_flag": True,
            "photo_evidence_provided": False,
            "prior_refund": False,
        },
        "policy_snippet": (
            "Policy exceptions for high-value customers may be considered, but any active chargeback or fraud marker "
            "requires escalation to fraud review. Do not issue refunds directly when fraud review is required."
        ),
        "known_facts": [
            "Customer is platinum tier.",
            "A prior agent mentioned an exception.",
            "A replacement shipment is already active.",
            "The account currently has an active chargeback flag.",
        ],
        "missing_fields": [],
        "phase": "initial",
        "feedback": None,
        "last_action_error": None,
    }


def build_initial_state(task_id: str) -> dict[str, Any]:
    factories = {
        "easy_refund_eligible": _easy_state,
        "medium_missing_info_tech_issue": _medium_state,
        "hard_policy_edge_case": _hard_state,
    }
    return deepcopy(factories[task_id]())


def _grade_easy(action: Action, state: dict[str, Any]) -> tuple[float, dict[str, float], str]:
    reason_codes = _serialize_enum_list(action.reason_codes)
    breakdown = {
        "decision_correct": 0.50 if action.decision == Decision.refund else 0.0,
        "reason_damaged_item": 0.10 if "damaged_item" in reason_codes else 0.0,
        "reason_within_return_window": 0.10 if "within_return_window" in reason_codes else 0.0,
        "priority_correct": 0.10 if action.priority == Priority.medium else 0.0,
        "no_unnecessary_escalation": 0.10 if action.escalation_team == EscalationTeam.none else 0.0,
        "no_unnecessary_request_info": 0.10 if action.decision != Decision.request_info and not action.request_fields else 0.0,
    }
    score = _normalize_task_score(sum(breakdown.values()))
    if score >= 0.85:
        feedback = "Direct refund is appropriate: damage is documented and within policy."
    else:
        feedback = "This case can be refunded directly without escalation or extra verification."
    return score, breakdown, feedback


def _maybe_reveal_medium_details(action: Action, state: dict[str, Any]) -> None:
    requested = _serialize_enum_list(action.request_fields)
    if {"order_id", "device_model"}.issubset(requested):
        state["phase"] = "final_resolution"
        state["missing_fields"] = []
        state["known_facts"].extend(
            [
                "Verified order_id: ORD-5508.",
                "Verified device_model: BlendPro BX-2.",
                "Purchase was 8 days ago and delivery was 6 days ago.",
                "No physical damage is reported.",
            ]
        )
        state["order_snapshot"].update(
            {
                "order_id": "ORD-5508",
                "product_name": "BlendPro BX-2",
                "days_since_purchase": 8,
                "days_since_delivery": 6,
            }
        )
        state["conversation_history"].append(
            {
                "speaker": "system",
                "text": "Verification completed: order and device details were confirmed.",
            }
        )


def _grade_medium(action: Action, state: dict[str, Any]) -> tuple[float, dict[str, float], str]:
    reason_codes = _serialize_enum_list(action.reason_codes)
    request_fields = _serialize_enum_list(action.request_fields)
    recommended_steps = _serialize_enum_list(action.recommended_steps)

    if state["phase"] == "initial":
        raw = {
            "request_info_correct": 0.35 if action.decision == Decision.request_info else 0.0,
            "asks_order_id": 0.15 if "order_id" in request_fields else 0.0,
            "asks_device_model": 0.15 if "device_model" in request_fields else 0.0,
            "reason_missing_information": 0.15 if "missing_information" in reason_codes else 0.0,
            "priority_correct": 0.10 if action.priority == Priority.medium else 0.0,
            "no_premature_resolution": 0.10 if action.decision == Decision.request_info else 0.0,
        }
        phase1_raw = round(sum(raw.values()), 4)
        state["phase1_score_raw"] = phase1_raw
        state["phase1_breakdown_raw"] = raw
        _maybe_reveal_medium_details(action, state)
        weighted = {f"phase1_{key}": value * 0.45 for key, value in raw.items()}
        score = _normalize_task_score(sum(weighted.values()))
        if state["phase"] == "final_resolution":
            feedback = "The missing details were requested correctly. You can now resolve the case."
        else:
            feedback = "Request the missing order details before attempting troubleshooting or refund."
        return score, weighted, feedback

    raw_phase2 = {
        "decision_troubleshoot": 0.35 if action.decision == Decision.troubleshoot else 0.0,
        "step_confirm_power_source": 0.125 if "confirm_power_source" in recommended_steps else 0.0,
        "step_factory_reset": 0.125 if "factory_reset" in recommended_steps else 0.0,
        "reason_technical_issue": 0.15 if "technical_issue" in reason_codes else 0.0,
        "priority_correct": 0.10 if action.priority == Priority.medium else 0.0,
        "no_refund_or_escalation": 0.15 if action.decision == Decision.troubleshoot and action.escalation_team == EscalationTeam.none else 0.0,
    }
    phase1_raw = state.get("phase1_score_raw", 0.0)
    phase1_weighted = {f"phase1_{key}": value * 0.45 for key, value in state.get("phase1_breakdown_raw", {}).items()}
    phase2_weighted = {f"phase2_{key}": value * 0.55 for key, value in raw_phase2.items()}
    breakdown = {**phase1_weighted, **phase2_weighted}
    score = _normalize_task_score(sum(breakdown.values()))
    if phase1_raw >= 0.75 and sum(raw_phase2.values()) >= 0.85:
        feedback = "Correct: verification completed first, then first-line troubleshooting was applied."
    else:
        feedback = "After verification, the correct next move is troubleshooting rather than refunding."
    return score, breakdown, feedback


def _grade_hard(action: Action, state: dict[str, Any]) -> tuple[float, dict[str, float], str]:
    reason_codes = _serialize_enum_list(action.reason_codes)
    breakdown = {
        "decision_escalate": 0.30 if action.decision == Decision.escalate else 0.0,
        "team_fraud_review": 0.25 if action.escalation_team == EscalationTeam.fraud_review else 0.0,
        "priority_high": 0.10 if action.priority in {Priority.high, Priority.urgent} else 0.0,
        "reason_fraud_risk": 0.10 if "fraud_risk" in reason_codes else 0.0,
        "reason_policy_exception": 0.05 if "policy_exception" in reason_codes else 0.0,
        "reason_repeat_contact": 0.05 if "repeat_contact" in reason_codes else 0.0,
        "no_direct_refund": 0.10 if action.decision != Decision.refund else 0.0,
        "no_unnecessary_request_info": 0.05 if action.decision != Decision.request_info else 0.0,
    }
    score = _normalize_task_score(sum(breakdown.values()))
    if score >= 0.75:
        feedback = "Fraud review is the correct destination because a chargeback flag overrides the refund exception."
    else:
        feedback = "Do not issue a direct refund here. Active chargeback requires fraud review escalation."
    return score, breakdown, feedback


def grade_action(task_id: str, action: Action, state: dict[str, Any]) -> tuple[float, dict[str, float], str]:
    graders = {
        "easy_refund_eligible": _grade_easy,
        "medium_missing_info_tech_issue": _grade_medium,
        "hard_policy_edge_case": _grade_hard,
    }
    return graders[task_id](action, state)


HINTS = {
    "easy_refund_eligible": [
        None,
        None,
        "Damaged item plus photo evidence plus recent delivery means you usually do not need escalation.",
        "This is a straightforward refund case within policy.",
    ],
    "medium_missing_info_tech_issue": [
        None,
        "The case is missing key verification details.",
        "Ask for the missing order identifier and device model before deciding.",
        "After verification, first-line troubleshooting is the correct path.",
        "Refunding before verification would be premature.",
        None,
    ],
    "hard_policy_edge_case": [
        None,
        None,
        "A prior exception promise matters, but chargeback and fraud signals override normal refund handling.",
        "Think carefully about escalation destination before refunding.",
        "This case belongs in fraud review, not direct refund.",
        None,
    ],
}


def get_hint(task_id: str, step_number: int) -> str | None:
    hints = HINTS.get(task_id, [])
    if step_number < len(hints):
        return hints[step_number]
    return None


TASK_REGISTRY: dict[str, dict[str, Any]] = {
    "easy_refund_eligible": {
        "id": "easy_refund_eligible",
        "name": "Resolve Obvious Refund Eligibility",
        "difficulty": "easy",
        "description": (
            "A customer reports a damaged delivery with photo evidence already attached and the order is within the refund window. "
            "Choose the correct support resolution."
        ),
        "max_steps": 4,
        "reward_threshold": 0.85,
    },
    "medium_missing_info_tech_issue": {
        "id": "medium_missing_info_tech_issue",
        "name": "Request Missing Details Before Troubleshooting",
        "difficulty": "medium",
        "description": (
            "A customer reports a technical issue, but the support case is missing the order identifier and product model. "
            "Request the right information first, then choose the correct next action."
        ),
        "max_steps": 6,
        "reward_threshold": 0.80,
    },
    "hard_policy_edge_case": {
        "id": "hard_policy_edge_case",
        "name": "Handle a Fraud-Flagged Policy Exception",
        "difficulty": "hard",
        "description": (
            "An angry VIP customer is demanding an exception refund, but the account has an active chargeback flag and an in-flight replacement. "
            "Choose the correct policy-safe escalation path."
        ),
        "max_steps": 6,
        "reward_threshold": 0.75,
    },
}

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Decision(str, Enum):
    refund = "refund"
    troubleshoot = "troubleshoot"
    escalate = "escalate"
    close = "close"
    request_info = "request_info"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class EscalationTeam(str, Enum):
    none = "none"
    billing_review = "billing_review"
    logistics_ops = "logistics_ops"
    technical_support = "technical_support"
    fraud_review = "fraud_review"
    retention_desk = "retention_desk"


class ReasonCode(str, Enum):
    damaged_item = "damaged_item"
    technical_issue = "technical_issue"
    missing_information = "missing_information"
    within_return_window = "within_return_window"
    policy_exception = "policy_exception"
    fraud_risk = "fraud_risk"
    repeat_contact = "repeat_contact"


class RequestField(str, Enum):
    order_id = "order_id"
    device_model = "device_model"
    photo_evidence = "photo_evidence"
    delivery_date = "delivery_date"
    serial_number = "serial_number"


class TroubleshootStep(str, Enum):
    confirm_power_source = "confirm_power_source"
    factory_reset = "factory_reset"
    check_tracking = "check_tracking"
    verify_account_email = "verify_account_email"


class ConversationTurn(BaseModel):
    speaker: str
    text: str


class OrderSnapshot(BaseModel):
    order_id: Optional[str] = None
    product_name: Optional[str] = None
    days_since_purchase: Optional[int] = None
    days_since_delivery: Optional[int] = None
    replacement_active: bool = False
    chargeback_flag: bool = False
    photo_evidence_provided: bool = False
    prior_refund: bool = False


class Action(BaseModel):
    decision: Decision
    priority: Priority
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    request_fields: list[RequestField] = Field(default_factory=list)
    recommended_steps: list[TroubleshootStep] = Field(default_factory=list)
    escalation_team: EscalationTeam = EscalationTeam.none
    customer_message: Optional[str] = Field(
        default=None,
        description="Optional customer-facing response text",
    )


class Observation(BaseModel):
    task_id: str
    case_id: str
    task_description: str
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    customer_tier: str
    sentiment: str
    urgency: str
    order_snapshot: OrderSnapshot
    policy_snippet: str
    known_facts: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    phase: str
    feedback: Optional[str] = None
    hint: Optional[str] = None
    step_number: int = 0
    max_steps: int
    done: bool = False
    last_action_error: Optional[str] = None


class Reward(BaseModel):
    value: float = Field(..., ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: dict[str, Any] = Field(default_factory=dict)


class ResetRequest(BaseModel):
    task_id: str = Field(
        default="easy_refund_eligible",
        description="One of: easy_refund_eligible, medium_missing_info_tech_issue, hard_policy_edge_case",
    )
    session_id: Optional[str] = Field(default=None, description="Optional reusable session ID")


class ResetResponse(BaseModel):
    session_id: str
    observation: Observation


class StateResponse(BaseModel):
    session_id: str
    task_id: str
    phase: str
    step_number: int
    done: bool
    cumulative_reward: float
    best_score: float
    state: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class TaskInfo(BaseModel):
    id: str
    name: str
    difficulty: TaskDifficulty
    description: str
    max_steps: int
    reward_threshold: float
    action_schema: dict[str, Any]


class GraderRequest(BaseModel):
    session_id: str


class GraderResponse(BaseModel):
    session_id: str
    task_id: str
    final_score: float
    breakdown: dict[str, float]
    solved: bool
    done: bool


class BaselineResult(BaseModel):
    method: str
    model: str
    scores: dict[str, float]
    details: dict[str, Any]
    reproducible: bool


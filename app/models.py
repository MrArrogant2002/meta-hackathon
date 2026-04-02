from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class TaskDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Action(BaseModel):
    sql_query: str = Field(..., description="The SQL query submitted as an attempt")
    explanation: Optional[str] = Field(default=None, description="Agent's reasoning (optional)")


class ExecutionResult(BaseModel):
    success: bool
    rows: list[list[Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class Observation(BaseModel):
    task_id: str
    task_description: str
    broken_query: str
    schema_info: str
    error_message: Optional[str] = None
    last_submission: Optional[str] = None
    last_execution_result: Optional[ExecutionResult] = None
    hint: Optional[str] = None
    step_number: int = 0
    max_steps: int = 5
    done: bool = False


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
    task_id: str = Field(..., description="One of: easy_syntax_fix, medium_logic_fix, hard_optimization")
    session_id: Optional[str] = Field(default=None, description="Reuse existing session ID or omit to create new")


class ResetResponse(BaseModel):
    session_id: str
    observation: Observation


class StateResponse(BaseModel):
    session_id: str
    task_id: str
    step_number: int
    done: bool
    cumulative_reward: float
    best_score: float
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

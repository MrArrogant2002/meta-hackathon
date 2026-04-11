import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

SESSION_TTL_MINUTES = 30


@dataclass
class Session:
    session_id: str
    task_id: str
    state: dict[str, Any]
    step_number: int = 0
    done: bool = False
    cumulative_reward: float = 0.0
    best_score: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str, state: dict[str, Any], session_id: str | None = None) -> Session:
        sid = session_id or str(uuid.uuid4())
        session = Session(session_id=sid, task_id=task_id, state=state)
        with self._lock:
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_accessed = datetime.utcnow()
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def cleanup_expired(self) -> None:
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
        with self._lock:
            expired = [sid for sid, session in self._sessions.items() if session.last_accessed < cutoff]
            for sid in expired:
                del self._sessions[sid]

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


store = SessionStore()


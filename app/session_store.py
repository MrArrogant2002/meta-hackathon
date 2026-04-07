import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import sqlite3

SESSION_TTL_MINUTES = 30


@dataclass
class Session:
    session_id: str
    task_id: str
    db_conn: sqlite3.Connection
    step_number: int = 0
    done: bool = False
    cumulative_reward: float = 0.0
    best_score: float = 0.001  # Must be > 0.0 for Phase 2 validation
    history: list = field(default_factory=list)
    last_observation: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str, session_id: str | None = None) -> Session:
        from app.database import create_session_db
        sid = session_id or str(uuid.uuid4())
        conn = create_session_db()
        session = Session(session_id=sid, task_id=task_id, db_conn=conn)
        with self._lock:
            if sid in self._sessions:
                try:
                    self._sessions[sid].db_conn.close()
                except Exception:
                    pass
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_accessed = datetime.utcnow()
            return session

    def delete(self, session_id: str):
        with self._lock:
            if session_id in self._sessions:
                try:
                    self._sessions[session_id].db_conn.close()
                except Exception:
                    pass
                del self._sessions[session_id]

    def cleanup_expired(self):
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if s.last_accessed < cutoff
            ]
            for sid in expired:
                try:
                    self._sessions[sid].db_conn.close()
                except Exception:
                    pass
                del self._sessions[sid]

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# Singleton — shared across all requests
store = SessionStore()

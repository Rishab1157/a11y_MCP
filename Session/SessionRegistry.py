import uuid
from Session.Session import Session
from selenium.webdriver.remote.webdriver import WebDriver

IDLE_TIMEOUT = 1800          # 30 minutes

class SessionRegistry:
    """In-memory store of live browser sessions, keyed by session_id.

    MCP tools are stateless — a WebDriver cannot cross the JSON boundary.
    The driver stays here; the agent carries the session_id string.
    """
    
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        
    def add(self, driver: WebDriver) -> Session:
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = Session(driver=driver)
        return session_id
    
    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            known = list(self._sessions) or ["<none>"]
            raise ValueError(
                f"Unknown session_id {session_id!r}. Call create_driver first. "
                f"Open sessions: {known}"
            )
            
        session.touch()
        return session
    
    def close(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        try:
            session.driver.quit()
        except Exception:
            pass
        return True

    def reap_idle(self) -> list[str]:
        """Close sessions nobody has touched. Agents forget to call close."""
        dead = [sid for sid, s in self._sessions.items() if s.idle_seconds > IDLE_TIMEOUT]
        for sid in dead:
            self.close(sid)
        return dead
    
    def __len__(self) -> int:
        return len(self._sessions)


registry = SessionRegistry()

from typing import Optional
from pydantic import BaseModel

class SessionResult(BaseModel):
    """What session tools hand back to the agent.

    Crosses the MCP boundary, so it must be JSON-serializable —
    hence pydantic here rather than a dataclass.
    """

    ok: bool
    session_id: Optional[str] = None
    reached_target: Optional[bool] = None
    final_url: Optional[str] = None
    title: Optional[str] = None
    failure_reason: Optional[str] = None
    error: Optional[str] = None
    
    def model_dump(self, **kwargs):
        """Drop unset fields by default so the agent sees no null noise."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    @classmethod
    def failure(cls, error: str) -> "SessionResult":
        """The tool itself failed — Chrome would not start, bad config, etc."""
        return cls(ok=False, error=error)

    @classmethod
    def created(cls, session_id: str) -> "SessionResult":
        """A driver was created successfully."""
        return cls(ok=True, session_id=session_id)
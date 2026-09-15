import time
from dataclasses import dataclass, field
from selenium.webdriver.remote.webdriver import WebDriver

@dataclass(eq = False)
class Session:
    """One live browser, held in server memory between MCP tool calls."""
    
    driver: WebDriver = field(repr = False)
    last_used: float = field(default_factory = time.time)
    created_at: float = field(default_factory = time.time)
    current_url: str | None = None
    reached_target: bool = False
    
    def touch(self) -> None:
        """Mark this session as recently used, so it is not reaped."""
        self.last_used = time.time()
        
    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used
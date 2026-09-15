from typing import Optional, Literal
from pydantic import BaseModel, Field

from Config.DriverConfig import BrowserConfig


class CromeConfig(BrowserConfig):
    """Chrome configuration. Any field left unset is not applied at all."""
    
    browser: Literal["chrome"] = "chrome"
    zoom_percent: Optional[int] = Field(None, ge=100, le=500, description="Device scale, e.g. 400 for WCAG 1.4.10 reflow.")

    

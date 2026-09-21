from typing import Optional, Literal
from pydantic import Field

from Config.DriverConfig.BrowserConfig import BrowserConfig


class EdgeConfig(BrowserConfig):
    """Edge configuration. Edge is Chromium, so it honours exactly what Chrome does."""

    browser: Literal["edge"] = "edge"
    zoom_percent: Optional[int] = Field(None, ge=100, le=500, description="Device scale, e.g. 400 for WCAG 1.4.10 reflow.")

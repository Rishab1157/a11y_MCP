from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BrowserConfig(BaseModel):
    """Browser configuration. Any field left unset is not applied at all."""

    model_config = ConfigDict(extra="forbid")
    viewport_width: Optional[int] = Field(None, ge=320, le=7680)
    viewport_height: Optional[int] = Field(None, ge=240, le=4320)
    headless: Optional[bool] = Field(None, description="Run with no visible window.")
    user_agent: Optional[str] = Field(None, description="Override the user agent string.")
    extra_args: Optional[list[str]] = Field(None, description="Raw browser flags, escape hatch.")
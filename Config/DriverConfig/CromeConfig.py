from typing import Optional, Literal
from pydantic import BaseModel, Field

from Config.DriverConfig import BrowserConfig


class CromeConfig(BrowserConfig):
    """Chrome configuration. Any field left unset is not applied at all."""

    

from typing import Literal, Optional

from Config.DriverConfig import BrowserConfig


class FirefoxConfig(BrowserConfig):
    """Firefox configuration. Any field left unset is not applied at all."""
    
    browser: Literal["firefox"] = "firefox"
    profile_path: Optional[str] = None
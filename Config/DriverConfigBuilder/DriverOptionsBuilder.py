import logging
from abc import ABC, abstractmethod
from Config.DriverConfig import BrowserConfig
from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)


class UnsupportedOptionError(ValueError):
    """Raised when a config asks for something this browser cannot do."""

class DriverOptionsBuilder(ABC):
    """Translates a browser-agnostic config into one browser's options object."""
    
    browser_name: str
    supported: set[str]          # config fields this browser can honour
    
    @abstractmethod
    def _new_options(self): ...
    """Return a fresh options object with baseline flags applied."""
    
    @abstractmethod
    def _apply(self, cfg: BrowserConfig, opts) -> None: ...
    """Apply the config's set fields onto the options object."""
    
    @abstractmethod
    def create_driver(self, options) -> WebDriver:
        """Launch the browser with these options."""
    
    @staticmethod
    def _log_launch(driver: WebDriver) -> None:
        """One line per launch, same shape for every browser.

        Goes to the logging module rather than print() because stdout is
        block-buffered whenever it is not a terminal, which is exactly how
        this server runs.
        """
        caps = driver.capabilities or {}
        logger.info(
            "launched %s (session %s)",
            caps.get("browserName", "?"),
            driver.session_id,
        )
        logger.debug("capabilities: %s", caps)

    def build(self, cfg: BrowserConfig):
        requested = set(cfg.model_dump(exclude_none=True)) - {"browser"}
        unsupported = requested - self.supported

        if unsupported:
            raise UnsupportedOptionError(
                f"{self.browser_name} cannot honour {sorted(unsupported)}. "
                f"Supported: {sorted(self.supported)}"
            )

        opts = self._new_options()
        self._apply(cfg, opts)
        return opts


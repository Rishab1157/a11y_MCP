from abc import ABC, abstractmethod

from Config.DriverConfig import BrowserConfig


class DriverOptionsBuilder(ABC):
    browser_name: str
    supported: set[str]          # config fields this browser can honour
    
    @abstractmethod
    def _new_options(self): ...
    
    @abstractmethod
    def _apply(self, cfg: BrowserConfig, opts) -> None: ...
    
    def build(self, cfg: BrowserConfig):
        requested = set(cfg.model_dump(exclude_none=True))
        unsupported = requested - self.supported

        if unsupported:
            raise UnsupportedOptionError(
                f"{self.browser_name} cannot honour {sorted(unsupported)}. "
                f"Supported: {sorted(self.supported)}"
            )

        opts = self._new_options()
        self._apply(cfg, opts)
        return opts


class UnsupportedOptionError(ValueError):
    """Raised when a config asks for something this browser cannot do."""
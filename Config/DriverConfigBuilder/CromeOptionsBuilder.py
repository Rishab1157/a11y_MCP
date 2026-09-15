from selenium.webdriver.chrome.options import Options as ChromeOptions

from Config.DriverConfig import CromeConfig
from Config.DriverConfigBuilder import DriverOptionsBuilder

BASELINE = [
    "--disable-notifications",
    "--no-first-run",
    "--no-default-browser-check",
    "--log-level=3",
]


class CromeOptionsBuilder(DriverOptionsBuilder):
    browser_name = "Chrome",
    supported = {
        "headless", "viewport_width", "viewport_height",
        "user_agent", "zoom_percent", "extra_args",
    }
    
    def _new_options(self) -> ChromeOptions:
        opts = ChromeOptions()
        for arg in BASELINE:
            opts.add_argument(arg)
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        return opts
    
    def _apply(self, cfg: CromeConfig, opts: ChromeOptions) -> None:
        if cfg.headless:
            opts.add_argument("--headless=new")
        if cfg.viewport_width and cfg.viewport_height:
            opts.add_argument(f"--window-size={cfg.viewport_width},{cfg.viewport_height}")
        if cfg.user_agent:
            opts.add_argument(f"--user-agent={cfg.user_agent}")
        if cfg.zoom_percent:
            opts.add_argument(f"--force-device-scale-factor={cfg.zoom_percent / 100}")
        for arg in cfg.extra_args or []:
            opts.add_argument(arg)
    
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver import Chrome
from Config.DriverConfig import CromeConfig, EdgeConfig
from Config.DriverConfigBuilder import DriverOptionsBuilder

BASELINE = [
    "--disable-notifications",
    "--no-first-run",
    "--no-default-browser-check",
    "--log-level=3",
]


class CromeOptionsBuilder(DriverOptionsBuilder):
    browser_name = "Chrome"
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
    
    def _apply(self, cfg: CromeConfig | EdgeConfig, opts: ChromeOptions) -> None:
        if cfg.headless:
            opts.add_argument("--headless=new")
        if cfg.viewport_width or cfg.viewport_height:
            w = cfg.viewport_width or 1920
            h = cfg.viewport_height or 1080
            opts.add_argument(f"--window-size={w},{h}")
        if cfg.user_agent:
            opts.add_argument(f"--user-agent={cfg.user_agent}")
        if cfg.zoom_percent:
            opts.add_argument(f"--force-device-scale-factor={cfg.zoom_percent / 100}")
        for arg in cfg.extra_args or []:
            opts.add_argument(arg)
    
    def create_driver(self, opts: ChromeOptions) -> Chrome:
        chrome_driver = Chrome(options=opts)
        self._log_launch(chrome_driver)
        return chrome_driver
    
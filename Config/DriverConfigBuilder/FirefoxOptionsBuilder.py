# Config/DriverConfigBuilder/FirefoxOptionsBuilder.py
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from Config.DriverConfig import FirefoxConfig
from Config.DriverConfigBuilder.DriverOptionsBuilder import DriverOptionsBuilder


class FirefoxOptionsBuilder(DriverOptionsBuilder):
    browser_name = "Firefox"
    supported = {
        "headless", "viewport_width", "viewport_height",
        "user_agent", "extra_args", "profile_path",
    }

    def _new_options(self) -> FirefoxOptions:
        opts = FirefoxOptions()
        opts.set_preference("browser.shell.checkDefaultBrowser", False)
        opts.set_preference("dom.webnotifications.enabled", False)
        return opts

    def _apply(self, cfg: FirefoxConfig, opts: FirefoxOptions) -> None:
        if cfg.headless:
            opts.add_argument("-headless")              # one dash, not two
        if cfg.viewport_width or cfg.viewport_height:
            opts.add_argument(f"--width={cfg.viewport_width or 1920}")
            opts.add_argument(f"--height={cfg.viewport_height or 1080}")
        if cfg.user_agent:
            opts.set_preference("general.useragent.override", cfg.user_agent)
        if cfg.profile_path:
            opts.add_argument("-profile")
            opts.add_argument(cfg.profile_path)
        for arg in cfg.extra_args or []:
            opts.add_argument(arg)

    def create_driver(self, opts: FirefoxOptions) -> Firefox:
        return Firefox(options=opts)

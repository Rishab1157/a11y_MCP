from selenium.webdriver import Edge
from selenium.webdriver.edge.options import Options as EdgeOptions

from Config.DriverConfigBuilder.CromeOptionsBuilder import BASELINE, CromeOptionsBuilder


class EdgeOptionsBuilder(CromeOptionsBuilder):
    """Edge is Chromium: every flag _apply() sets is accepted unchanged, so only
    the options class and the driver differ.

    Worth having because msedgedriver.exe is signed by Microsoft while
    chromedriver.exe is not signed at all, so Edge still starts on machines
    where code-signing policy refuses to run the Chrome driver.
    """

    browser_name = "Edge"

    def _new_options(self) -> EdgeOptions:
        opts = EdgeOptions()
        for arg in BASELINE:
            opts.add_argument(arg)
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        return opts

    def create_driver(self, opts: EdgeOptions) -> Edge:
        edge_driver = Edge(options=opts)
        self._log_launch(edge_driver)
        return edge_driver

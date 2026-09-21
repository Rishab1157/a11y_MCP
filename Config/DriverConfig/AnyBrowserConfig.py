from typing import Annotated

from pydantic import Field

from Config.DriverConfig.CromeConfig import CromeConfig
from Config.DriverConfig.FirefoxConfig import FirefoxConfig
from Config.DriverConfig.EdgeConfig import EdgeConfig

AnyBrowserConfig = Annotated[
    CromeConfig | FirefoxConfig | EdgeConfig,
    Field(discriminator="browser"),
]
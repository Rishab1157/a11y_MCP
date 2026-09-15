from typing import Annotated

from pydantic import Field

from Config.DriverConfig.CromeConfig import CromeConfig
from Config.DriverConfig.FirefoxConfig import FirefoxConfig

AnyBrowserConfig = Annotated[
    CromeConfig | FirefoxConfig,
    Field(discriminator="browser"),
]
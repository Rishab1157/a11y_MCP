from Config.DriverConfigBuilder import CromeOptionsBuilder, DriverOptionsBuilder, FirefoxOptionsBuilder


_BUILDERS: dict[str, DriverOptionsBuilder] = {
    "chrome", CromeOptionsBuilder(),
    "firefox", FirefoxOptionsBuilder()
}


def get_builder(browser: str) -> DriverOptionsBuilder:
    """Return the options builder for a browser name."""
    builder = _BUILDERS.get(browser)
    if builder is None:
        raise ValueError(
            f"No builder for browser {browser!r}. Available: {sorted(_BUILDERS)}"
        )
    return builder
from .AxTreeReader import (
    AxTreeReader,
    AxTreeUnsupportedError,
    FirefoxAxTreeReader,
    get_reader,
    register,
)
from .ChromiumAxTreeReader import ChromiumAxTreeReader
from .PageReady import wait_for_page_ready

register(FirefoxAxTreeReader())

__all__ = [
    "AxTreeReader",
    "AxTreeUnsupportedError",
    "ChromiumAxTreeReader",
    "FirefoxAxTreeReader",
    "get_reader",
    "register",
    "wait_for_page_ready",
]
from abc import ABC, abstractmethod
from selenium.webdriver.remote.webdriver import WebDriver

class AxTreeUnsupportedError(RuntimeError):
    """Raised when a browser has no accessibility-tree implementation yet."""
    
class AxTreeReader(ABC):
    """Reads an accessibility tree and normalises it to one shape.

    Every implementation must return:
        {
          "ax_source":          "cdp" | "computed"
          "ax_engine":          str   which engine produced it
          "ax_engine_version":  str
          "total_exposed":      int
          "interactive_count":  int
          "unnamed_interactive": list  interactive nodes with an empty name
          "roles_seen":         list
          "nodes":              list  {role, name, description, properties, interactive, node_id, backend_id}
        }

    Downstream tools consume that shape and never learn which browser or
    mechanism produced it — except through the provenance fields, which
    matter because a computed tree models the spec while CDP returns the
    browser's own tree.
    """
    
    browser: str
    ax_source: str
    ax_engine: str

    @abstractmethod
    def read(self, driver: WebDriver) -> dict:
        """Return the normalised accessibility tree for the current page."""

_READERS: dict[str, AxTreeReader] = {}

def register(reader: AxTreeReader) -> None:
    """Make a reader available to get_reader()."""
    _READERS[reader.browser] = reader


def get_reader(browser: str) -> AxTreeReader:
    reader = _READERS.get(browser)
    if reader is None:
        raise AxTreeUnsupportedError(
            f"No accessibility-tree reader for {browser!r}. "
            f"Available: {sorted(_READERS)}"
        )
    return reader
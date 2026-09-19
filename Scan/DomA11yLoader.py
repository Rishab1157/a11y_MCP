"""Loads dom-accessibility-api into the page as window.domA11y.

The vendored file is an ES module, so a plain execute_script cannot define
anything from it. It has to go through a blob URL and a dynamic import(),
which is asynchronous — hence execute_async_script.

Vendored from https://cdn.jsdelivr.net/npm/dom-accessibility-api@0.7.1/+esm
Pin the version: the filename is the provenance record.
"""

from pathlib import Path
from selenium.webdriver.remote.webdriver import WebDriver

BUNDLE = Path(__file__).parent / "vendor" / "dom-accessibility-api-0.7.1.esm.js"
BUNDLE_VERSION = "0.7.1"

EXPECTED_EXPORTS = {
    "computeAccessibleDescription",
    "computeAccessibleName",
    "getRole",
    "isDisabled",
    "isInaccessible",
    "isSubtreeInaccessible",
}

_LOADER = """
const done = arguments[arguments.length - 1];
const source = arguments[0];
try {
    const blob = new Blob([source], {type: 'text/javascript'});
    const url  = URL.createObjectURL(blob);
    import(url)
        .then(mod => { window.domA11y = mod; URL.revokeObjectURL(url); done(null); })
        .catch(err => done('import failed: ' + String(err)));
} catch (e) {
    done('blob failed: ' + String(e));
}
"""

def inject_dom_a11y(driver: WebDriver) -> None:
    """Make window.domA11y available on the current page.

    The global does not survive navigation, so this runs per page — but it
    returns immediately if the page already has it.
    """
    
    if driver.execute_script("return typeof window.domA11y !== 'undefined';"):
        return
    
    if not BUNDLE.exists():
        raise FileNotFoundError(
            f"Vendored bundle missing: {BUNDLE}. Fetch it with:\n"
            f"  curl -o {BUNDLE} "
            f"https://cdn.jsdelivr.net/npm/dom-accessibility-api@{BUNDLE_VERSION}/+esm"
        )
        
    driver.set_script_timeout(30)
    error = driver.execute_async_script(_LOADER, BUNDLE.read_text(encoding="utf-8"))
    if error:
        raise RuntimeError(
            f"Could not load dom-accessibility-api: {error}. "
            f"A strict Content-Security-Policy can block blob: scripts, and "
            f"import() needs a real document rather than about:blank."
        )
    missing = EXPECTED_EXPORTS - set(
        driver.execute_script("return Object.keys(window.domA11y);")
    )
    
    if missing:
        raise RuntimeError(
            f"Bundle loaded but is missing expected exports: {sorted(missing)}. "
            f"The vendored version may not be {BUNDLE_VERSION}."
        )
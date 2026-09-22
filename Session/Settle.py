import time

from selenium.common import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

_SAMPLE = """
return [location.href, document.getElementsByTagName('*').length];
"""


def wait_until_settled(driver: WebDriver, timeout: float = 10.0, stable_for: float = 0.6, poll: float = 0.1) -> dict:
    """Wait until the app has stopped navigating and rendering.

    driver.get() returns when the initial document is complete. A single-page
    app then runs its router, which may redirect — QXcel bounces /stories to
    /projects when no project is selected. Sampling current_url before that
    reports the URL that was requested, not the one that was reached.

    Watches the URL and the DOM node count together: the URL proves the route
    settled, the node count proves the new route finished rendering. Returns
    as soon as both hold still for `stable_for` seconds, so a page that never
    redirects costs about `stable_for`, not `timeout`.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if driver.execute_script("return document.readyState") == "complete":
            break
        time.sleep(poll)

    last, since = None, None
    while time.time() < deadline:
        try:
            now = tuple(driver.execute_script(_SAMPLE))
        except WebDriverException:
            last, since = None, None
            time.sleep(poll)
            continue

        if now == last:
            if since is None:
                since = time.time()
            elif time.time() - since >= stable_for:
                return {"settled": True, "final_url": now[0], "node_count": now[1]}
        else:
            last, since = now, None
        time.sleep(poll)

    return {
        "settled": False,
        "final_url": driver.current_url,
        "node_count": last[1] if last else -1,
        "note": f"still changing after {timeout}s - the page may poll or animate",
    }

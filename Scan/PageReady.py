import time
from selenium.webdriver.remote.webdriver import WebDriver

def wait_for_page_ready(driver: WebDriver, timeout: int = 15, stable_for: float = 0.6) -> dict:
    """Wait until the document is loaded AND the DOM has stopped changing.

    driver.get() returns when the document is ready, but a single-page app
    renders its content afterwards. Scanning before that returns an empty
    page and reports it as clean.

    Returns as soon as the page settles — a fast page costs well under a
    second. Only a page that never settles costs the full timeout.
    """
    
    deadline = time.time() + timeout
    
    # 1. document.readyState
    while time.time() < deadline:
        if driver.execute_script("return document.readyState") == "complete":
            break
        time.sleep(0.1)
        
    # 2. DOM quiescence — node count unchanged for `stable_for` seconds
    last_count, stable_since = -1, None
    while time.time() < deadline:
        count = driver.execute_script(
            "return document.getElementsByTagName('*').length"
        )
        
        if count == last_count:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_for:
                return {
                    "settled": True, "node_count": count,
                    "waited": round(timeout - (deadline - time.time()), 2)
                }
        else:
            last_count = count
            stable_since = None
        time.sleep(0.2)
        
    return {
        "settled": False, "node_count": last_count, "waited": timeout,
        "note": "DOM never stopped changing - page may poll or animate."
    }
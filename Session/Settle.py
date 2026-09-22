import time

from selenium.common import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

# as a preload script and inside execute_script.
_COUNTER_SRC = """
if (!window.__a11yInstalled) {
    window.__a11yInstalled = true;
    window.__a11yInflight = 0;

    // Never let the counter go negative: a decrement can fire for a request
    const dec = () => { window.__a11yInflight = Math.max(0, window.__a11yInflight - 1); };

    const of = window.fetch;
    if (of) {
        window.fetch = function (...a) {
            window.__a11yInflight++;
            return of.apply(this, a).finally(dec);
        };
    }

    const os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (...a) {
        window.__a11yInflight++;
        this.addEventListener('loadend', dec, { once: true });
        return os.apply(this, a);
    };
}
"""

# BiDi takes a function declaration, not a script body. Passing bare statements
# is accepted and then silently never runs, so a successful call proves nothing.
_PRELOAD_SRC = _COUNTER_SRC + """
window.__a11yPreloaded = true;"""

_PRELOAD_FN = f"""() => {{
{_PRELOAD_SRC}
}}"""


_SAMPLE = _COUNTER_SRC + """
return [
        location.href,
        document.getElementsByTagName('*').length,
        window.__a11yInflight || 0,
        !!window.__a11yPreloaded
    ];
"""

def arm_settle_hooks(driver: WebDriver) -> str:
    """Install the counter so it runs before any page script, on every document.

    Without this the hooks land only after driver.get() returns, by which time
    an inline <script> has already issued the request the app is gated on — and
    an untracked request is indistinguishable from an idle page. Verified: with
    post-hoc installation the settle returns /review at 0.75s; armed here it
    returns /projects at 2.31s, and a page that does not redirect still settles
    in 0.76s.
    Returns the mechanism used, for the session log.
    """
    
    try:                                   # Chromium (Chrome, Edge)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": _PRELOAD_SRC}
        )
        return "cdp"
    except Exception:
        pass

    try:                                   # WebDriver BiDi — Firefox included
        driver.script.add_preload_script(_PRELOAD_FN)
        return "bidi"
    except Exception:
        return "none"                      # falls back to per-poll installation
    
    

def wait_until_settled(driver: WebDriver, timeout: float = 10.0, stable_for: float = 0.6, poll: float = 0.1) -> dict:
    """Wait until the app has stopped navigating.

    URL stability is the signal that decides the result: QXcel bounces /stories
    to /projects once React finds no project selected, long after driver.get()
    returned.

    DOM element count and tracked fetch/XHR activity are supporting signals,
    not proof that the app is idle. They miss WebSocket traffic, image and
    script loads and service workers; a React app can also change meaningful
    state without changing its element count. They are here to stop the window
    closing while the app is visibly still working, and are reported for
    diagnosis.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                break
        except WebDriverException:
            pass
        time.sleep(poll)

    last, since = None, None
    preloaded = False

    while time.time() < deadline:
        try:
            now = tuple(driver.execute_script(_SAMPLE))
        except WebDriverException:
            last, since = None, None
            time.sleep(poll)
            continue

        url, nodes, inflight, preloaded = now

        if preloaded and inflight > 0:
            since = None                   # something the app started is outstanding
            last = now
            time.sleep(poll)
            continue

        if now == last:
            if since is None:
                since = time.time()
            elif time.time() - since >= stable_for:
                return {"settled": True, "final_url": url, "node_count": nodes, "inflight": inflight, "preloaded": preloaded}
        else:
            last, since = now, None

        time.sleep(poll)

    try:
        final_url = driver.current_url
    except WebDriverException:
        final_url = last[0] if last else ""

    return {
        "settled": False,
        "final_url": final_url,
        "node_count": last[1] if last else -1,
        "inflight": last[2] if last else -1,
        "preloaded": preloaded,
        "note": f"still changing after {timeout}s - the app may poll, animate or hold "
        f"an open request. final_url is a snapshot, not a settled value.",
    }
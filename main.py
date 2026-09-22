import logging
import sys

from fastmcp import FastMCP
from urllib.parse import urlparse
from Auth import AnyAuthConfig, get_provider
from Session import SessionResult, registry, detect_auth_scheme, verify_arrival, Target, find_all, Step, _run_steps, classify_failure, same_page
from Config.DriverConfig import AnyBrowserConfig, CromeConfig
from Config.DriverConfigBuilder import UnsupportedOptionError, get_builder
from Scan import AxTreeUnsupportedError, get_reader, wait_for_page_ready

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)

mcp = FastMCP("a11y MCP server")

@mcp.tool()
def create_driver(config: AnyBrowserConfig | None = None) -> dict:
    """Create a browser session for accessibility testing.

    Set "browser" to "chrome", "edge" or "firefox". Options differ per browser —
    Chrome and Edge support zoom_percent, Firefox supports profile_path.

    Chrome and Edge are both Chromium and produce identical accessibility
    trees. If "chrome" fails to start, retry with "edge" before reporting
    failure — some machines refuse to run the unsigned Chrome driver.
    Anything omitted uses the browser's default.

    Returns a session_id required by every other a11y tool.
    Always call close_session when the audit is finished.
    """
    
    registry.reap_idle()
    cfg = config or CromeConfig()
    
    try:
        builder = get_builder(cfg.browser)
        options = builder.build(cfg)
        driver = builder.create_driver(options)
    except (UnsupportedOptionError, ValueError) as e:
        return SessionResult.failure(str(e)).model_dump(exclude_none=True)
    except Exception as e:
        return SessionResult.failure(
            f"{cfg.browser} failed to start: {type(e).__name__}: {e}"
        ).model_dump(exclude_none=True)
        
    return SessionResult.created(registry.add(driver, cfg.browser)).model_dump(exclude_none=True)


@mcp.tool()
def close_session(session_id: str) -> dict:
    """Close a browser session and free its process."""
    
    if registry.close(session_id):
        return {"ok": True, "closed": session_id}
    return SessionResult.failure(
        f"Unknown session_id: {session_id}"
    ).model_dump(exclude_none=True)
    
    
@mcp.tool()
def list_sessions() -> dict:
    """List how many browser sessions are currently open."""
    
    return {"ok": True, "open_sessions": len(registry)}


@mcp.tool()
def navigate(session_id: str, url: str, success_check: str = "") -> dict:
    """Navigate to a URL and verify the page was actually reached.

    Returns reached_target=false when the browser landed on a login wall
    instead, along with an "auth" report listing every usable auth mode
    ranked by likelihood. Pass the top option to authenticate().

    Call this before every scan — a session can expire mid-crawl, and
    scanning a login page produces a report about the wrong page.

    Args:
        session_id: From create_driver.
        url: Full URL including scheme.
        success_check: Text that only appears once the real page has loaded,
            e.g. "My Projects". The strongest proof of arrival.
    """
    
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://"}
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "code": "unknown_session", "error": str(e)}
    
    try:
        session.driver.get(url)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    
    check = verify_arrival(session.driver, url, success_check)
    session.reached_target = check["reached"]
    session.verified_url = check["final_url"] if check["reached"] else None
    
    result = {
        "ok": True,
        "reached_target": check["reached"],
        "final_url": check["final_url"],
        "title": check["title"],
    }
    
    if not check["reached"]:
        result["reasons"] = check["reasons"]
        result["failure_kind"] = classify_failure(session.driver, check["final_url"], url)
        
        if result["failure_kind"] == "auth":
            result["auth"] = detect_auth_scheme(session.driver)
        elif result["failure_kind"] == "prerequisite":
            result["hint"] = (
                "The app redirected to another of its own pages, so the session is "
                "authenticated but this route needs application state that is not set "
                "- a selected project, workspace or similar. Use reach_state with "
                "steps that establish it."
            )
    return result


@mcp.tool()
def authenticate(session_id: str, auth: AnyAuthConfig, target_url: str, success_check: str = "") -> dict:
    """Authenticate a browser session so protected pages can be scanned.

    Call navigate() first. When it reports reached_target=false it returns an
    "auth" report whose "options" are ranked by likelihood, each naming what
    it requires. Use the top option here.

    On failure, TRY THE NEXT OPTION rather than reporting failure. A page that
    offers both a login form and an SSO button may reject form credentials —
    the report already listed token and api as fallbacks, and the failed
    response returns the ranked list again.

    Choosing a mode:
      none     page is public, or navigate() already reached it
      token    you already hold a token. Works with SSO and MFA, since the
               token is obtained outside this tool
      api      the app exposes a login endpoint returning a token. Also covers
               identity-provider client-credentials flows
      form     a username and password form is on the page. Cannot pass SSO,
               MFA or CAPTCHA
      storage  replay cookies and localStorage exported from a real session

    Returns two separate facts:
      authenticated   the credentials were accepted
      reached_target  target_url itself was reached

    They differ when a page needs application state: being redirected to
    another page of the same app proves you are logged in, and reach_state
    is the tool for establishing what the page was missing.

    authenticated=false means credentials were applied but access is still
    refused — read "reasons", "hint" and "auth.options" before retrying.

    Args:
        session_id: From create_driver.
        auth: Auth configuration; its "mode" selects the method.
        target_url: Protected page used to confirm authentication succeeded.
        success_check: Text that only appears once the real page has loaded.
    """
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    driver = session.driver

    # Where the browser must be before the provider runs, depends on the mode:
    #   token/storage/api - inject into storage, which is origin-scoped
    #   form              - needs to be looking at the actual login page
    #   none              - nothing to do
    if auth.mode in ("token", "storage", "api"):
        landing = "{0.scheme}://{0.netloc}".format(urlparse(target_url))
    elif auth.mode == "form" and not auth.login_url:
        landing = target_url          # usually redirects to the real login page
    else:
        landing = None

    if landing:
        try:
            driver.get(landing)
        except Exception as e:
            return {"ok": False, "error": f"could not reach {landing}: {e}"}

    try:
        applied = get_provider(auth.mode).apply(driver, auth)
    except Exception as e:
        return {"ok": False, "mode": auth.mode, "error": f"{type(e).__name__}: {e}"}

    driver.get(target_url)
    check = verify_arrival(driver, target_url, success_check)
    session.reached_target = check["reached"]   
    session.verified_url = check["final_url"] if check["reached"] else None
    
    failure_kind = None
    if not check["reached"]:
        failure_kind = classify_failure(driver, check["final_url"], target_url)
    
    authenticated = check["reached"] or failure_kind == "prerequisite"

    result = {
        "ok": True,
        "mode": auth.mode,
        "authenticated": authenticated,
        "reached_target": check["reached"],     
        "final_url": check["final_url"],
        "applied": applied,
    }
    
    if not check["reached"]:
        result["reasons"] = check["reasons"]
        result["failure_kind"] = failure_kind
        
        if failure_kind == "prerequisite":
            result["hint"] = (
                "Authentication succeeded. This page was refused because it needs "
                "application state that is not set - a selected project, workspace or "
                "similar. Use reach_state with steps that establish it, and pick a "
                "state-free page for target_url next time."
            )
        elif failure_kind in ("auth", "unknown"):
            result["auth"] = detect_auth_scheme(driver)

            if auth.mode == "none":
                result["hint"] = (
                    "This page requires authentication but auth.mode was 'none'. "
                    "Retry with one of the modes listed in auth.recommended_modes."
                )
            elif auth.mode in ("token", "storage"):
                result["hint"] = (
                    "Credentials were applied but the page still redirects. The token "
                    "may have expired, or storage_key may not match the key the app "
                    "actually reads. Check DevTools > Application > Local Storage."
                )
            elif auth.mode == "api":
                result["hint"] = (
                    "The login API responded but the session is still rejected. "
                    "Check that token_field named the right key, and that storage_key "
                    "matches what the app reads."
                )
            elif auth.mode == "form":
                result["hint"] = (
                    "The form was submitted but access is still denied. Credentials may "
                    "be wrong, or the site may require a second factor that form mode "
                    "cannot satisfy."
                )
    return result


@mcp.tool()
def get_accessibility_tree(session_id: str, include_all_nodes: bool = False, page_timeout: int = 15) -> dict:
    """Read the accessibility tree — the structure screen readers consume.

    Returns the computed role, accessible name and state of every element the
    browser exposes to assistive technology. This is how WCAG 4.1.2 is tested:
    the criterion requires name, role and state to be programmatically
    determinable, and this tree is what "programmatically determinable" means.

    Interactive elements with an empty name are 4.1.2 failures and come back
    separately as unnamed_interactive.

    Check ax_source on the result. "cdp" is the browser's own tree; "computed"
    is derived from the DOM and models the spec rather than reporting it.

    Args:
        session_id: From create_driver.
        include_all_nodes: Return every exposed node. Off by default because a
            real page yields hundreds and the summary carries the findings.
        page_timeout: Seconds to wait for the page to finish rendering. Raise
            it for slow servers or heavy single-page apps. Returns as soon as
            the page settles, so a higher value costs nothing on a fast page.
    """
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "code": "unknown_session", "error": str(e)}
    
    if not session.reached_target:
        return {
            "ok": False,
            "code": "not_on_target",
            "error": "The last navigation did not reach the target page. "
                    "Scanning now would audit a login or error page. "
                    "Call navigate() or reach_state() first.",
        }
        
    if not session.verified_url:
        return {
            "ok": False,
            "code": "not_on_target",
            "error": "Session is marked verified but no verified URL was recorded. "
                    "Call navigate() or reach_state() again before scanning.",
        }
    
    if not same_page(session.driver.current_url, session.verified_url):
        return {
            "ok": False,
            "code": "page_changed",
            "error": f"The page moved since it was verified: {session.verified_url} "
                    f"-> {session.driver.current_url}. Call navigate() or "
                    f"reach_state() again before scanning.",
        }

        
    ready = wait_for_page_ready(session.driver, timeout=page_timeout)
    
    try:
        tree = get_reader(session.browser).read(session.driver)
    except AxTreeUnsupportedError as e:
        return {"ok": False, "code": "unsupported_browser", "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    
    if not include_all_nodes:
        tree.pop("nodes", None)
        
    return {"ok": True, "page_ready": ready, **tree}


@mcp.tool()
def resolve_target(session_id: str, target: Target) -> dict:
    """Check whether a Target resolves to exactly one element, without acting.

    Use this to build a workflow: probe each target first, confirm it matches
    one element, then run the steps. An ambiguous or missing target is far
    cheaper to find here than halfway through a workflow that has already
    changed application state.

    A target that cannot be found by accessible name is itself an accessibility
    finding — a screen reader user could not identify that control either.
    """
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "code": "unknown_session", "error": str(e)}
    
    try:
        matches, described = find_all(session.driver, target)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    
    result = {"ok": True, "matched": len(matches), "candidates": described}
    if not matches:
        result["hint"] = (
            "No matching element found. Check the target name, role, or CSS selector."
        )
    elif len(matches) > 1:
        result["hint"] = (
            "Multiple elements matched. Refine the target or use `nth` if the position is known and stable."
        )
    return result
    

@mcp.tool()
def run_steps(
        session_id: str, steps: list[Step], dry_run: bool = False, 
        allow_destructive: bool = False, page_timeout: int = 15
    ) -> dict:
    """Drive the application through a sequence of UI actions.

    Each step acts on one target and then checks its own expectations. Targets
    are located by accessible name, so workflows survive class-name changes
    and re-renders.

    Run with dry_run=true first: it resolves every target without acting, so a
    typo in step 12 fails in seconds instead of half-completing the workflow.

    Steps that look irreversible — Delete, Log out, Pay — are refused unless
    allow_destructive is set.

    Returns a trail: what each step did, which expectation proved it, and where
    it stopped. Read the trail on failure; it names the exact assertion that
    was not met.
    """
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "code": "unknown_session", "error": str(e)}

    return _run_steps(session.driver, steps, dry_run, allow_destructive, page_timeout)


@mcp.tool()
def reach_state(
        session_id: str, target_url: str, steps: list[Step] | None = None,
        success_check: str = "", allow_destructive: bool = False
    ) -> dict:
    """Get the application into a specific state, then confirm it.

    Some pages depend on state that only exists in application memory — a
    selected project, a chosen workspace. Navigating straight to such a URL
    redirects away, and scanning what you land on audits the wrong page.

    This navigates, and if the target was not reached, runs the supplied steps
    to establish the prerequisite, then navigates again and re-verifies.

    Sets reached_target on the session, which every scan tool checks. Scans are
    refused until this succeeds.

    Args:
        session_id: From create_driver.
        target_url: The page to end up on.
        steps: Actions that establish the prerequisite state, e.g. selecting a
            project. Omit when the page has no prerequisites.
        success_check: Text that only appears once the real page has loaded.
            The strongest proof of arrival.
    """
    
    try:
        session = registry.get(session_id)
    except ValueError as e:
        return {"ok": False, "code": "unknown_session", "error": str(e)}

    driver = session.driver
    trail = {}

    try:
        driver.get(target_url)
    except Exception as e:
        return {"ok": False, "error": f"could not reach {target_url}: {e}"}
    
    check = verify_arrival(driver, target_url, success_check)
    session.reached_target = check["reached"]
    session.verified_url = check["final_url"] if check["reached"] else None
    
    if not check["reached"] and steps:
        trail["steps"] = _run_steps(driver, steps, allow_destructive=allow_destructive)
        if not trail["steps"]["ok"]:
            session.reached_target = False
            return {
                "ok": True,
                "reached_target": False,
                "reason": "prerequisite step falied",
                "final_url": driver.current_url , **trail
            }
            
        try:
            driver.get(target_url)            # retry now that state exists
        except Exception as e:
            return {"ok": False, "error": f"could not reach {target_url}: {e}"}
        check = verify_arrival(driver, target_url, success_check)

    session.reached_target = check["reached"]
    session.verified_url = check["final_url"] if check["reached"] else None

    result = {
        "ok": True,
        "reached_target": check["reached"],
        "requested_url": target_url,
        "final_url": check["final_url"],
        "title": check["title"], **trail,
    }
    if not check["reached"]:
        result["reasons"] = check["reasons"]
        result["failure_kind"] = classify_failure(driver, check["final_url"], target_url)

        if result["failure_kind"] == "auth":
            result["auth"] = detect_auth_scheme(driver)
            result["hint"] = (
                "The page is behind an authentication wall. Call authenticate() "
                "with one of the modes in auth.options before retrying."
            )
        elif result["failure_kind"] == "prerequisite":
            if steps:
                result["hint"] = (
                    "The steps ran but this route still needs application state they "
                    "did not establish. Re-check them with run_steps(dry_run=true)."
                )
            else:
                result["hint"] = (
                    "The app redirected to another of its own pages. Supply steps that "
                    "establish the prerequisite state - selecting a project, workspace "
                    "or similar."
                )
        elif not steps:
            result["hint"] = "The page redirected and no steps were supplied"
    return result

        
        

def main():
    mcp.run(transport = "streamable-http", host = "0.0.0.0", port = 8081)

if __name__ == "__main__":
    main()
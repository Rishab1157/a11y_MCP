from urllib.parse import urlparse

from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from Session.Settle import wait_until_settled

from Auth import LOGIN_WORDS, SSO_HOSTS, SSO_TEXT_HINTS, PASSWORD_GUESSES, USERNAME_GUESSES

def _host(netloc: str) -> str:
    return netloc.lower().removeprefix("www.")


def same_page(a: str, b: str) -> bool:
    """Same host and path. Scheme is ignored on purpose — an http -> https
    upgrade is not a redirect away from the target."""
    pa, pb = urlparse(a), urlparse(b)
    return (_host(pa.netloc) == _host(pb.netloc)
            and (pa.path.rstrip("/") or "/") == (pb.path.rstrip("/") or "/"))

def verify_arrival(driver: WebDriver, target_url: str, success_check: str = "", timeout: int = 10, settle_timeout: float = 10.0) -> dict:
    """Check whether the browser actually reached the target page.

    Returns reached=False with reasons when it landed on a login wall or a
    different page instead. Never assume a navigation succeeded — that is how
    a scan ends up auditing a login screen and reporting it as the application.
    """

    # 1. Let the SPA router finish. Nothing below is meaningful until it has:
    # driver.get() returns at document-ready, and the redirect comes after.
    settle = wait_until_settled(driver, timeout=settle_timeout)

    reasons: list[str] = []

    # 2. The caller's own proof of arrival — strongest signal. 
    if success_check:
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: success_check in (
                    d.execute_script("return document.body.innerText || '';") or ""
                )
            )
        except TimeoutException:
            reasons.append(
                f"expected text {success_check!r} not found after {timeout}s"
            )

    # 3. Sample AFTER all waiting, never before.
    current = driver.current_url
    title = driver.title or ""

    # 4. Redirected somewhere else?
    if not same_page(current, target_url):
        reasons.append(f"redirected to {current}")

    # 5. Password field on screen means a login form
    if _first_match(driver, PASSWORD_GUESSES) and _first_match(driver, USERNAME_GUESSES):
        reasons.append("visible username and password fields - this is a login page")

    # 6. Title gives it away
    lowered = title.lower()
    if any(word in lowered for word in LOGIN_WORDS):
        reasons.append(f"title looks like a login page: {title!r}")

    # 7. Bounced to an identity provider
    host = urlparse(current).netloc.lower()
    for sso in SSO_HOSTS:
        if sso in host:
            reasons.append(f"redirected to identity provider {host}")
            break

    return {
        "reached": not reasons,
        "final_url": current,
        "title": title,
        "reasons": reasons,
        "settled": settle["settled"],
    }


def _first_match(driver, selectors):
    for css in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, css):
            if el.is_displayed() and el.is_enabled():
                return el
    return None

def classify_failure(driver: WebDriver, current: str, target_url: str) -> str:
    """Why did we not arrive? Auth and application state need different fixes.

    Returning "auth" for a state problem sends the agent off to re-enter
    credentials that were never wrong.
    """
    # A real login form: visible username AND password
    if _first_match(driver, PASSWORD_GUESSES) and _first_match(driver, USERNAME_GUESSES):
        return "auth"

    host = urlparse(current).netloc.lower()
    if any(s in host for s in SSO_HOSTS):
        return "auth"

    if any(w in (driver.title or "").lower() for w in LOGIN_WORDS):
        return "auth"

    if host == urlparse(target_url).netloc.lower():
        return "prerequisite"

    return "unknown"

def detect_auth_scheme(driver: WebDriver) -> dict:
    """Report which auth modes can work on the current page, best first.

    Uses the same selector lists as FormAuthProvider, so it never rules out
    form mode for a field the provider would have found.
    """
    password_el = _first_match(driver, PASSWORD_GUESSES)
    username_el = _first_match(driver, USERNAME_GUESSES)

    sso_candidates = []
    for el in driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button']"):
        if not el.is_displayed():
            continue
        text = (el.text or "").strip()
        href = (el.get_attribute("href") or "").lower()
        matched_text = next((h for h in SSO_TEXT_HINTS if h in text.lower()), None)
        matched_host = next((h for h in SSO_HOSTS if h in href), None)
        if matched_text or matched_host:
            sso_candidates.append({
                "text": text[:60],
                "matched_on": matched_host or matched_text,
                "href": href[:120] or None,
            })

    host = urlparse(driver.current_url).netloc.lower()
    on_sso_host = any(s in host for s in SSO_HOSTS)
    has_form = bool(password_el and username_el)
    has_sso = bool(sso_candidates or on_sso_host)

    # Keyed by mode so a mode can never be listed twice.
    modes: dict[str, dict] = {}

    if has_form:
        modes["form"] = {
            "mode": "form",
            "confidence": "high",
            "why": "Username and password fields are present. The app's own "
                   "JavaScript stores the token, so no storage_key is needed.",
            "requires": ["username", "password"],
            "caveat": "Fails if the site asks for an OTP after submitting.",
        }

    modes["api"] = {
        "mode": "api",
        "confidence": "high" if (has_sso and not has_form) else "medium",
        "why": ("Interactive SSO cannot be automated, but the provider usually "
                "offers a machine-to-machine flow (client credentials) needing "
                "no browser or OTP."
                if has_sso else
                "Most apps expose the login endpoint their own form calls."),
        "requires": ["login_endpoint", "payload", "token_field",
                     "storage_key", "storage_type"],
        "caveat": "Find the endpoint in DevTools > Network while logging in "
                  "manually. The only mode that runs unattended after deployment.",
    }

    modes["token"] = {
        "mode": "token",
        "confidence": "medium" if has_sso else "low",
        "why": "Log in once in a browser, then copy the credential the app "
               "stores. Check DevTools > Application under Local Storage, "
               "Session Storage and Cookies to find which one holds it.",
        "requires": ["token", "storage_key", "storage_type"],
        "caveat": "Manual step, expires within hours.",
    }

    modes["storage"] = {
        "mode": "storage",
        "confidence": "low",
        "why": "Replaying a real session works regardless of how login happened.",
        "requires": ["local_storage or session_storage or cookies"],
        "caveat": "Needs a human to export it first; expires like a token.",
    }

    rank = {"high": 0, "medium": 1, "low": 2}
    options = sorted(modes.values(), key=lambda o: rank[o["confidence"]])

    return {
        "protected": has_form or has_sso,
        "options": options,
        "has_form": has_form,
        "has_sso": has_sso,
        "evidence": {
            "password_field_found": password_el is not None,
            "username_field_found": username_el is not None,
            "sso_candidates": sso_candidates[:5],
            "host": host,
        },
    }

from urllib.parse import urlparse

from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC

from Auth import LOGIN_WORDS, SSO_HOSTS, SSO_TEXT_HINTS, PASSWORD_GUESSES, USERNAME_GUESSES

def verify_arrival(driver: WebDriver, target_url: str, success_check: str = "", timeout: int = 10) -> dict:
    """Check whether the browser actually reached the target page.

    Returns reached=False with reasons when it landed on a login wall instead.
    Never assume a navigation succeeded — that is how a scan ends up
    auditing a login screen and reporting it as the application.
    """
    
    reasons: list[str] = []
    current = driver.current_url
    title = driver.title or ""
    
    # 1. Redirected somewhere else?
    if urlparse(current).path.rstrip("/") != urlparse(target_url).path.rstrip("/"):
        reasons.append(f"redirected to {current}")
        
    # 2. Password field on screen means a login form
    if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
        reasons.append("password field present - this is a login page")
        
    # 3. Title gives it away
    lowered = title.lower()
    if any(word in lowered for word in LOGIN_WORDS):
        reasons.append(f"title looks like a login page: {title!r}")
        
    # 4. Bounced to an identity provider
    host = urlparse(current).netloc.lower()
    for sso in SSO_HOSTS:
        if sso in host:
            reasons.append(f"redirected to identity provider {host}")
            break
        
    # 5. The caller's own proof of arrival — strongest signal
    if success_check:
        xpath = f"//*[contains(normalize-space(.), {success_check!r})]"
        
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        except TimeoutException:
            reasons.append(
                f"expected text {success_check!r} not found after {timeout}s"
            )
            
    return {
        "reached": not reasons,
        "final_url": current,
        "title": title,
        "reasons": reasons,
    }

def _first_match(driver, selectors):
    for css in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, css):
            if el.is_displayed() and el.is_enabled():
                return el
    return None

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
        "protected": True,
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

import requests
from abc import ABC, abstractmethod
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver

from Auth.AuthConfig import ApiAuth, FormAuth, NoAuth, StorageAuth, TokenAuth
from Auth.Selectors import PASSWORD_GUESSES, SUBMIT_GUESSES, USERNAME_GUESSES


def _find(driver: WebDriver, selector: str | None, guesses: list[str]):
    """Find an element by an explicit selector, or by trying common patterns."""
    
    candidates = [selector] if selector else guesses
    for css in candidates:
        for el in driver.find_elements(By.CSS_SELECTOR, css):
            if el.is_displayed() and el.is_enabled():
                return el
    return None

def _inject(driver: WebDriver, key: str, value: str, storage_type: str) -> None:
    """Write a token into browser storage. Must already be on the target origin."""
    
    match storage_type:
        case "local":
            driver.execute_script(
                "window.localStorage.setItem(arguments[0], arguments[1]);", key, value
            )

        case "session":
            driver.execute_script(
                "window.sessionStorage.setItem(arguments[0], arguments[1]);", key, value
            )

        case "cookie":
            driver.add_cookie(
                { "name": key, "value": value, "path": "/" }
            )

        case _:
            raise ValueError(f"Unknown storage_type: {storage_type!r}")
        
        
class AuthProvider(ABC):
    """Applies one authentication method to a live browser session."""

    mode: str

    @abstractmethod
    def apply(self, driver: WebDriver, cfg) -> dict:
        """Perform the auth. Does NOT verify it worked — that is a separate step."""


class NoAuthProvider(AuthProvider):
    mode = "none"

    def apply(self, driver: WebDriver, cfg: NoAuth) -> dict:
        return {"applied": "none"}
    

class TokenAuthProvider(AuthProvider):
    mode = "token"

    def apply(self, driver: WebDriver, cfg: TokenAuth) -> dict:
        _inject(driver, cfg.storage_key, cfg.token, cfg.storage_type)
        return {"applied": "token", "storage_key": cfg.storage_key,
                "storage_type": cfg.storage_type}
    

class ApiAuthProvider(AuthProvider):
    mode = "api"

    def apply(self, driver: WebDriver, cfg: ApiAuth) -> dict:
        response = requests.post(
            cfg.login_endpoint, json=cfg.payload,
            headers=cfg.headers or {}, timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Login API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        body = response.json()
        if cfg.token_field not in body:
            raise RuntimeError(
                f"token_field {cfg.token_field!r} not in response. "
                f"Keys present: {sorted(body)}"
            )

        _inject(driver, cfg.storage_key, body[cfg.token_field], cfg.storage_type)
        return {"applied": "api", "storage_key": cfg.storage_key,
                "http_status": response.status_code}
        
        
class FormAuthProvider(AuthProvider):
    mode = "form"
    
    def apply(self, driver: WebDriver, cfg: FormAuth) -> dict:
        if cfg.login_url:
            driver.get(cfg.login_url)

        user_el = _find(driver, cfg.username_selector, USERNAME_GUESSES)
        pass_el = _find(driver, cfg.password_selector, PASSWORD_GUESSES)

        if user_el is None or pass_el is None:
            raise RuntimeError(
                "Could not find a username/password field. The page may use SSO. "
                "Use mode 'token' or 'api' instead."
            )

        user_el.clear()
        user_el.send_keys(cfg.username)
        pass_el.clear()
        pass_el.send_keys(cfg.password)

        submit = _find(driver, cfg.submit_selector, SUBMIT_GUESSES)
        if submit:
            submit.click()
        else:
            pass_el.send_keys(Keys.RETURN)

        return {"applied": "form", "submitted_via": "button" if submit else "enter"}
    
    
class StorageAuthProvider(AuthProvider):
    mode = "storage"

    def apply(self, driver: WebDriver, cfg: StorageAuth) -> dict:
        counts = {"local_storage": 0, "session_storage": 0, "cookies": 0}

        for k, v in cfg.local_storage.items():
            _inject(driver, k, v, "local")
            counts["local_storage"] += 1
        for k, v in cfg.session_storage.items():
            _inject(driver, k, v, "session")
            counts["session_storage"] += 1
        for cookie in cfg.cookies:
            try:
                driver.add_cookie(cookie)
                counts["cookies"] += 1
            except Exception:
                pass          # wrong domain or expired — skip it

        return {"applied": "storage", **counts}


_PROVIDERS: dict[str, AuthProvider] = {
    p.mode: p for p in (
        NoAuthProvider(), TokenAuthProvider(), ApiAuthProvider(),
        FormAuthProvider(), StorageAuthProvider(),
    )
}


def get_provider(mode: str) -> AuthProvider:
    provider = _PROVIDERS.get(mode)
    if provider is None:
        raise ValueError(f"No provider for auth mode {mode!r}. Available: {sorted(_PROVIDERS)}")
    return provider
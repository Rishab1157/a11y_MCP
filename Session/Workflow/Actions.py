"""Generic interaction primitives.

Every action re-resolves its Target. Handles are never carried between steps —
React re-renders and a cached WebElement goes stale, which is the most common
source of flakiness in workflow engines.
"""

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver

from Session.Workflow.Models import Step, Target
from Session.Workflow.Resolver import resolve

KEYS = {
    "ENTER": Keys.ENTER, "TAB": Keys.TAB, "ESCAPE": Keys.ESCAPE,
    "SPACE": Keys.SPACE, "BACKSPACE": Keys.BACKSPACE, "DELETE": Keys.DELETE,
    "ARROW_UP": Keys.ARROW_UP, "ARROW_DOWN": Keys.ARROW_DOWN,
    "ARROW_LEFT": Keys.ARROW_LEFT, "ARROW_RIGHT": Keys.ARROW_RIGHT,
    "HOME": Keys.HOME, "END": Keys.END, "PAGE_UP": Keys.PAGE_UP,
    "PAGE_DOWN": Keys.PAGE_DOWN,
}

# Reads the live checked state. aria-checked wins over the DOM property because
# a custom control may use the attribute without being a real <input>.
_IS_CHECKED = """
const el = arguments[0];
const aria = el.getAttribute('aria-checked');
if (aria !== null) return aria === 'true';
if (el.checked !== undefined) return !!el.checked;
const inner = el.querySelector('input[type=checkbox], input[type=radio], [aria-checked]');
if (inner) {
    const a = inner.getAttribute('aria-checked');
    if (a !== null) return a === 'true';
    return !!inner.checked;
}
return null;                       // state not exposed — cannot reconcile
"""

_SET_VALUE = """
const el = arguments[0], value = arguments[1];
if (el.isContentEditable) {
    el.focus();
    el.textContent = value;
    el.dispatchEvent(new InputEvent('input', {bubbles: true}));
    return true;
}
return false;                      // a normal field — let Selenium type it
"""


class ActionError(RuntimeError):
    """The action could not be performed."""


def perform(driver: WebDriver, step: Step) -> dict:
    """Run one step's action. Returns what happened, for the trail."""
    action = step.action

    if action == "navigate":
        if not step.value:
            raise ActionError("navigate requires `value` to be a URL")
        driver.get(step.value)
        return {"action": "navigate", "url": step.value}

    if step.target is None:
        raise ActionError(f"{action} requires a target")

    element = resolve(driver, step.target)          # always fresh
    _scroll_into_view(driver, element)

    if action == "click":
        element.click()
        return {"action": "click", "clicked": True}

    if action == "scroll_to":
        return {"action": "scroll_to", "scrolled": True}

    if action == "hover":
        from selenium.webdriver import ActionChains
        ActionChains(driver).move_to_element(element).perform()
        return {"action": "hover", "hovered": True}

    if action == "press":
        key = KEYS.get((step.value or "").upper())
        if key is None:
            raise ActionError(
                f"Unknown key {step.value!r}. Supported: {sorted(KEYS)}"
            )
        element.send_keys(key)
        return {"action": "press", "key": step.value}

    if action == "fill":
        if step.value is None:
            raise ActionError("fill requires `value`")
        current = element.get_attribute("value") or element.text or ""
        if current == step.value:
            return {"action": "fill", "skipped": "already set", "value": step.value}
        if not driver.execute_script(_SET_VALUE, element, step.value):
            element.clear()
            element.send_keys(step.value)
        return {"action": "fill", "was": current[:60], "now": step.value[:60]}

    if action in ("ensure_checked", "ensure_unchecked"):
        want = action == "ensure_checked"
        current = driver.execute_script(_IS_CHECKED, element)

        if current is None:
            raise ActionError(
                f"{_name(step.target)} exposes no checked state, so it cannot be "
                f"reconciled. Use `click` if you know the current state, or fix "
                f"the control to expose aria-checked (WCAG 4.1.2)."
            )
        if current == want:
            return {"action": action, "skipped": "already correct", "checked": current}

        element.click()
        after = driver.execute_script(_IS_CHECKED, resolve(driver, step.target))
        return {"action": action, "was": current, "now": after}

    raise ActionError(f"Unknown action: {action}")


def _scroll_into_view(driver: WebDriver, element) -> None:
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element
    )


def _name(target: Target) -> str:
    return repr(target.name) if target.name else "target"

"""Generic interaction primitives.

Every action re-resolves its Target. Handles are never carried between steps —
React re-renders and a cached WebElement goes stale, which is the most common
source of flakiness in workflow engines.
"""

from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver

from Session.Workflow.Models import Step, Target
from Session.Workflow.Resolver import describe, resolve

KEYS = {
    "ENTER": Keys.ENTER, "TAB": Keys.TAB, "ESCAPE": Keys.ESCAPE,
    "SPACE": Keys.SPACE, "BACKSPACE": Keys.BACKSPACE, "DELETE": Keys.DELETE,
    "ARROW_UP": Keys.ARROW_UP, "ARROW_DOWN": Keys.ARROW_DOWN,
    "ARROW_LEFT": Keys.ARROW_LEFT, "ARROW_RIGHT": Keys.ARROW_RIGHT,
    "HOME": Keys.HOME, "END": Keys.END,
    "PAGE_UP": Keys.PAGE_UP, "PAGE_DOWN": Keys.PAGE_DOWN,
}

# <div class="custom-checkbox">
#     <input type="checkbox" checked>
# </div> inner to resolve the inner stuff if parent dosen't contain
_IS_CHECKED = """
const el = arguments[0];
const aria = el.getAttribute('aria-checked');
if (aria !== null) return aria === 'true';
if (el.checked !== undefined && el.checked !== null) return !!el.checked;
const inner = el.querySelector('input[type=checkbox], input[type=radio], [aria-checked]');
if (inner) {
    const a = inner.getAttribute('aria-checked');
    if (a !== null) return a === 'true';
    if (inner.checked !== undefined) return !!inner.checked;
}
return null;
"""

# Rich-text editors ignore send_keys and need the input event dispatched.
_SET_CONTENTEDITABLE = """
const el = arguments[0], value = arguments[1];
if (!el.isContentEditable) return false;
el.focus();
el.textContent = value;
el.dispatchEvent(new InputEvent('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return true;
"""

_READ_VALUE = """
const el = arguments[0];
if (el.value !== undefined && el.value !== null) return el.value;
if (el.isContentEditable) return el.textContent;
return null;
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

    if action == "scroll_to":
        return {"action": "scroll_to", "scrolled": True}

    if action == "click":
        element.click()
        return {"action": "click", "clicked": describe(step.target)}

    if action == "hover":
        ActionChains(driver).move_to_element(element).perform()
        return {"action": "hover", "hovered": describe(step.target)}

    if action == "press":
        key = KEYS.get((step.value or "").upper())
        if key is None:
            raise ActionError(
                f"Unknown key {step.value!r}. Supported: {', '.join(sorted(KEYS))}"
            )
        element.send_keys(key)
        return {"action": "press", "key": step.value}

    if action == "fill":
        if step.value is None:
            raise ActionError("fill requires `value`")
        current = driver.execute_script(_READ_VALUE, element) or ""
        if current == step.value:
            return {"action": "fill", "skipped": "already set",
                    "value": step.value[:60]}
        if not driver.execute_script(_SET_CONTENTEDITABLE, element, step.value):
            element.clear()
            element.send_keys(step.value)
        return {"action": "fill", "was": current[:60], "now": step.value[:60]}

    if action in ("ensure_checked", "ensure_unchecked"):
        want = action == "ensure_checked"
        current = driver.execute_script(_IS_CHECKED, element)

        if current is None:
            raise ActionError(
                f"{describe(step.target)} exposes no checked state, so it cannot "
                f"be reconciled — clicking it blind could toggle it the wrong way. "
                f"Use `click` if you already know the state, or fix the control to "
                f"expose aria-checked (WCAG 4.1.2)."
            )
        if current == want:
            return {"action": action, "skipped": "already correct",
                    "checked": current}

        element.click()
        # after = driver.execute_script(_IS_CHECKED, resolve(driver, step.target))
        return {"action": action, "was": current, "requested": want}

    raise ActionError(f"Unknown action: {action}")


def _scroll_into_view(driver: WebDriver, element) -> None:
    """Selenium's click auto-scrolls; hover and press do not, and lazily
    rendered content needs it regardless."""
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        element,
    )

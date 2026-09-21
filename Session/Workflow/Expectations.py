"""Verifies that a step actually worked.

Polls until satisfied or timeout — never sleeps a fixed amount. A fast page
costs milliseconds; only a genuine failure costs the full timeout.

Strength order, strongest first:
    state  >  appears / disappears  >  text_contains  >  text_changes_in

text_changes_in proves something changed, not that the intended state was
reached. It is the anchor of last resort, for applications that expose no
explicit state at all.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from Session.Workflow.Models import Expect, Target
from Session.Workflow.Resolver import (
    AmbiguousTargetError,
    TargetNotFoundError,
    find_all,
    resolve,
)

POLL_SECONDS = 0.4

# Live state read off the element. `value` is deliberately read from the DOM
# rather than the AX tree — it is a live property, not tree metadata, and is
# not in KEEP_PROPERTIES.
_READ_STATE = """
const el = arguments[0];
const aria = n => el.getAttribute('aria-' + n);
const out = {};
out.checked  = aria('checked') !== null ? aria('checked') === 'true'
             : (el.checked !== undefined ? !!el.checked : null);
out.expanded = aria('expanded') !== null ? aria('expanded') === 'true' : null;
out.selected = aria('selected') !== null ? aria('selected') === 'true' : null;
out.disabled = el.disabled === true || aria('disabled') === 'true';
out.required = el.required === true || aria('required') === 'true';
out.readonly = el.readOnly === true || aria('readonly') === 'true';
out.invalid  = aria('invalid');
out.value    = el.value !== undefined ? el.value
             : (el.isContentEditable ? el.textContent : null);
return out;
"""


class ExpectationFailed(AssertionError):
    """The expectation was not satisfied within its timeout."""


def snapshot_before(driver: WebDriver, expect: Expect | None) -> str | None:
    """Capture what text_changes_in needs to compare against, before the action."""
    if expect is None or expect.text_changes_in is None:
        return None
    try:
        return resolve(driver, expect.text_changes_in).text
    except (TargetNotFoundError, AmbiguousTargetError):
        return None            # absent now, appearing later still counts as a change


def verify(driver: WebDriver, expect: Expect | None,
           target: Target | None = None, before: str | None = None) -> dict:
    """Poll until the expectation holds. Raises ExpectationFailed on timeout."""
    if expect is None:
        return {"verified": False, "note": "no expectation given"}

    deadline = time.time() + expect.timeout
    last = None

    while time.time() < deadline:
        ok, detail = _check(driver, expect, target, before)
        last = detail
        if ok:
            return {"verified": True, "via": detail,
                    "waited": round(expect.timeout - (deadline - time.time()), 2)}
        time.sleep(POLL_SECONDS)

    raise ExpectationFailed(
        f"Expectation not met within {expect.timeout}s. Last observed: {last}"
    )


def _check(driver, expect: Expect, target, before):
    # 1. explicit accessibility state — strongest
    if expect.state is not None:
        if target is None:
            return False, "state expected but the step had no target"
        try:
            element = resolve(driver, target)
        except (TargetNotFoundError, AmbiguousTargetError) as e:
            return False, f"target not resolvable: {e}"
        actual = driver.execute_script(_READ_STATE, element)
        for key, want in expect.state.model_dump(exclude_none=True):
            if key not in actual:
                return False, f"unknown state key {key!r}; readable: {sorted(actual)}"
            if actual[key] != want:
                return False, f"{key}={actual[key]!r}, expected {want!r}"
        return True, f"state {expect.state}"

    # 2. an element appeared or disappeared
    if expect.appears is not None:
        found, _ = find_all(driver, Target(name=expect.appears))
        return (bool(found), f"{expect.appears!r} {'appeared' if found else 'not present yet'}")

    if expect.disappears is not None:
        found, _ = find_all(driver, Target(name=expect.disappears))
        return (not found, f"{expect.disappears!r} {'gone' if not found else 'still present'}")

    # 3. text present somewhere on the page
    if expect.text_contains is not None:
        body = driver.find_element(By.TAG_NAME, "body").text
        hit = expect.text_contains in body
        return hit, f"{expect.text_contains!r} {'found' if hit else 'not found'}"

    # 4. weakest — something changed
    if expect.text_changes_in is not None:
        try:
            now = resolve(driver, expect.text_changes_in).text
        except (TargetNotFoundError, AmbiguousTargetError) as e:
            return False, f"comparison target not resolvable: {e}"
        changed = now != before
        return changed, ("text changed" if changed
                         else f"text unchanged ({(now or '')[:40]!r})")

    return True, "expectation object was empty"

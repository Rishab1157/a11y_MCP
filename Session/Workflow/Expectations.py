"""Verifies that a step actually worked.

Polls until satisfied or timeout — never sleeps a fixed amount. A fast page
costs milliseconds; only a genuine failure costs the full timeout.

Every Expect resolves its own target against the CURRENT DOM, after the
action. Nothing is inherited from the Step: after a navigation the element
that was acted on may not exist any more.

Strength order, strongest first:
    state  >  appears / disappears  >  text_contains  >  text_changed
"""

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from Session.Workflow.Models import Expect, Step
from Session.Workflow.Resolver import (
    AmbiguousTargetError,
    TargetNotFoundError,
    describe,
    exists,
    resolve,
)
from Session.Workflow.Models import Target

POLL_SECONDS = 0.4

# `value` is read live from the DOM rather than the AX tree — it is a live
# property, not tree metadata, and is deliberately absent from KEEP_PROPERTIES.
_READ_STATE = """
const el = arguments[0];
const aria = n => el.getAttribute('aria-' + n);
return {
    checked:  aria('checked')  !== null ? aria('checked')  === 'true'
            : (el.checked !== undefined && el.checked !== null ? !!el.checked : null),
    expanded: aria('expanded') !== null ? aria('expanded') === 'true' : null,
    selected: aria('selected') !== null ? aria('selected') === 'true' : null,
    disabled: el.disabled === true || aria('disabled') === 'true',
    required: el.required === true || aria('required') === 'true',
    readonly: el.readOnly === true || aria('readonly') === 'true',
    invalid:  aria('invalid'),
    value:    el.value !== undefined && el.value !== null ? el.value
            : (el.isContentEditable ? el.textContent : null),
};
"""


class ExpectationFailed(AssertionError):
    """An expectation was not satisfied within its timeout."""


def snapshot_before(driver: WebDriver, step: Step) -> dict[int, str | None]:
    """Capture baselines for every text_changed expectation, keyed by index.

    Must run BEFORE the action. An element that does not exist yet has a
    baseline of None — appearing later then counts as a change.
    """
    baselines: dict[int, str | None] = {}
    for i, expect in enumerate(step.expects):
        if not expect.text_changed or expect.target is None:
            continue
        try:
            baselines[i] = resolve(driver, expect.target).text
        except (TargetNotFoundError, AmbiguousTargetError):
            baselines[i] = None
    return baselines


def verify_all(driver: WebDriver, step: Step, baselines: dict[int, str | None]) -> list[dict]:
    """Check every expectation in order. Raises on the first that fails.

    Sequential rather than concurrent: predictable, and the trail can say
    which assertion failed. Timeouts therefore add up.
    """
    results = []
    for i, expect in enumerate(step.expects):
        results.append(_verify_one(driver, expect, i, len(step.expects), baselines.get(i)))
    return results


def _verify_one(driver: WebDriver, expect: Expect, index: int, total: int, baseline: str | None) -> dict:
    deadline = time.time() + expect.timeout
    started = time.time()
    last = None

    while time.time() < deadline:
        ok, detail = _check(driver, expect, baseline)
        last = detail
        if ok:
            return {
                "expectation": f"{index + 1} of {total}",
                "label": expect.label,
                "verified": True,
                "via": detail,
                "seconds": round(time.time() - started, 2),
            }
        time.sleep(POLL_SECONDS)

    raise ExpectationFailed(
        f"Expectation {index + 1} of {total}"
        + (f" ({expect.label})" if expect.label else "")
        + f" not met within {expect.timeout}s. Last observed: {last}"
    )


def _check(driver: WebDriver, expect: Expect, baseline: str | None):
    # 1. explicit accessibility state — strongest
    if expect.state is not None:
        try:
            element = resolve(driver, expect.target)
        except (TargetNotFoundError, AmbiguousTargetError) as e:
            return False, f"target not resolvable: {e}"
        actual = driver.execute_script(_READ_STATE, element)
        wanted = expect.state.model_dump(exclude_none=True)
        for key, want in wanted.items():
            if actual.get(key) != want:
                return False, f"{key}={actual.get(key)!r}, expected {want!r}"
        return True, f"state {wanted} on {describe(expect.target)}"

    # 2. an element appeared or disappeared
    if expect.appears is not None:
        found = exists(driver, Target(name=expect.appears))
        return found, (f"{expect.appears!r} "
                       f"{'appeared' if found else 'not present yet'}")

    if expect.disappears is not None:
        found = exists(driver, Target(name=expect.disappears))
        return (not found), (f"{expect.disappears!r} "
                             f"{'gone' if not found else 'still present'}")

    # 3. text anywhere on the page
    if expect.text_contains is not None:
        body = driver.find_element(By.TAG_NAME, "body").text
        hit = expect.text_contains in body
        return hit, f"{expect.text_contains!r} {'found' if hit else 'not found'}"

    # 4. weakest — something changed
    if expect.text_changed:
        try:
            now = resolve(driver, expect.target).text
        except (TargetNotFoundError, AmbiguousTargetError):
            # Present before and gone now is also a change.
            return (baseline is not None), "target no longer resolvable"
        changed = now != baseline
        return changed, ("text changed" if changed else f"text unchanged ({(now or '')[:40]!r})")

    return True, "expectation asserted nothing"

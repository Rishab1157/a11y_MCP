"""Runs a list of Steps and returns a trail of what happened.

The trail is the point: a workflow that fails at step 12 of 17 has to say
which step, which expectation, what it was looking for and what it saw
instead. Without that a failed workflow is unfixable.
"""

import time

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common import StaleElementReferenceException
from Settle import wait_until_settled
from Session.Workflow.Actions import ActionError, perform
from Session.Workflow.Expectations import (
    ExpectationFailed,
    snapshot_before,
    verify_all,
)
from Session.Workflow.Models import Step
from Session.Workflow.Resolver import (
    AmbiguousTargetError,
    TargetNotFoundError,
    describe,
    find_all,
)

# Names that indicate an irreversible action. A workflow may still click them,
# but only when the caller has explicitly said so.
DESTRUCTIVE_HINTS = (
    "delete", "remove", "destroy", "deactivate", "archive",
    "cancel subscription", "log out", "logout", "sign out",
    "pay", "purchase", "checkout", "confirm order",
)


class DestructiveStepBlocked(PermissionError):
    """A step targets something irreversible and allow_destructive was not set."""


STEP_ERRORS = (TargetNotFoundError, AmbiguousTargetError, ActionError, ExpectationFailed, DestructiveStepBlocked, StaleElementReferenceException)


def run_steps(driver: WebDriver, steps: list[Step],  dry_run: bool = False,
            allow_destructive: bool = False, page_timeout: int = 15) -> dict:
    """Execute steps in order, stopping at the first failure.

    dry_run resolves every target without acting, so a broken config is caught
    before step 1 changes anything.
    """
    trail: list[dict] = []
    started = time.time()

    for index, step in enumerate(steps, start=1):
        entry = {"step": index, "action": step.action}
        if step.target is not None:
            entry["target"] = describe(step.target)
        step_started = time.time()

        try:
            if not allow_destructive:
                _refuse_if_destructive(step)

            if dry_run:
                entry.update(_dry_run_step(driver, step))
            else:
                baselines = snapshot_before(driver, step)       # before acting
                
                try:
                    entry["result"] = perform(driver, step)
                except StaleElementReferenceException:
                    wait_until_settled(driver, timeout=page_timeout)
                    entry["retried"] = "stale element; re-resolved and retried once"
                    entry["result"] = perform(driver, step)

                # Let the DOM settle before asserting, or an expectation can
                # match stale content from the page being left behind.
                entry["settled"] = wait_until_settled(driver, timeout=page_timeout)
                entry["expectations"] = verify_all(driver, step, baselines)

            entry["ok"] = True
            entry["seconds"] = round(time.time() - step_started, 2)
            trail.append(entry)

        except STEP_ERRORS as e:
            entry.update(ok=False, error=str(e), error_type=type(e).__name__, seconds=round(time.time() - step_started, 2))
            trail.append(entry)
            return _result(False, trail, started, index, len(steps), dry_run)

        except Exception as e:
            entry.update(ok=False, error=f"{type(e).__name__}: {e}", error_type="Unexpected",seconds=round(time.time() - step_started, 2))
            trail.append(entry)
            return _result(False, trail, started, index, len(steps), dry_run)

    return _result(True, trail, started, len(steps), len(steps), dry_run)


def _dry_run_step(driver: WebDriver, step: Step) -> dict:
    """Resolve targets without acting, so a bad config fails before anything moves."""
    if step.action == "navigate":
        return {"dry_run": "would navigate", "url": step.value}

    if step.target is None:
        raise ActionError(f"{step.action} requires a target")

    matches, described = find_all(driver, step.target)
    if not matches:
        raise TargetNotFoundError(
            f"No accessible element matched {describe(step.target)}. If the "
            f"control exists visually it has no accessible name, which a screen "
            f"reader user would also be unable to identify (WCAG 4.1.2)."
        )
    if len(matches) > 1 and step.target.nth is None:
        raise AmbiguousTargetError(
            f"{describe(step.target)} matched {len(matches)} elements: "
            f"{described}. Narrow with `role` or `within`."
        )
    return {"dry_run": "target resolves", "matched": len(matches), "candidates": described}


def _refuse_if_destructive(step: Step) -> None:
    if step.action not in ("click", "press"):
        return
    name = ((step.target.name if step.target else "") or "").lower()
    hit = next((h for h in DESTRUCTIVE_HINTS if h in name), None)
    if hit:
        raise DestructiveStepBlocked(
            f"Step targets {step.target.name!r}, which looks irreversible "
            f"(matched {hit!r}). Pass allow_destructive=true to proceed."
        )


def _result(ok, trail, started, reached, total, dry_run) -> dict:
    out = {
        "ok": ok,
        "dry_run": dry_run,
        "steps_total": total,
        "steps_completed": reached if ok else reached - 1,
        "failed_at_step": None if ok else reached,
        "seconds": round(time.time() - started, 2),
        "trail": trail,
    }
    if not ok:
        out["error"] = trail[-1].get("error")
        out["hint"] = (
            "Steps before this one already ran and may have changed application "
            "state. Re-running from the start is safe only if every earlier step "
            "is idempotent — fill and ensure_* are, click generally is not."
        )
    return out

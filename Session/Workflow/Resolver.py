"""Resolves a Target to a live Selenium WebElement via accessible name.

execute_script can return a WebElement, so the lookup runs in the page using
the same dom-accessibility-api bundle the Firefox reader uses — one
implementation for both browsers.

Filter order:  within → name/role → css → nth → ambiguity check
"""

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from Scan.DomA11yLoader import inject_dom_a11y
from Session.Workflow.Models import Target


class TargetNotFoundError(LookupError):
    """No element matched. Often an accessibility finding, not just a bad config."""


class AmbiguousTargetError(LookupError):
    """Several elements matched and nothing narrowed it. Never guess."""


_FIND = r"""
const spec  = arguments[0];
const scope = arguments[1] || document;
const api   = window.domA11y;

function nameOf(el) {
    try { return (api.computeAccessibleName(el) || '').replace(/\s+/g, ' ').trim(); }
    catch (e) { return ''; }
}
function roleOf(el) {
    try {
        let r = api.getRole(el);
        if (r === null) {
            const t = el.tagName.toLowerCase();
            if (t === 'svg' || t === 'canvas') r = 'img';
        }
        return r;
    } catch (e) { return null; }
}
function visible(el) {
    try {
        if (api.isInaccessible(el)) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    } catch (e) { return false; }
}

const wantName = spec.name ? spec.name.replace(/\s+/g, ' ').trim().toLowerCase() : null;
const wantRole = spec.role || null;
const wantCss  = spec.css  || null;

if (!wantName && !wantRole && !wantCss) {
    return {elements: [], count: 0, described: [], error: 'empty target'};
}

// Validate the selector once rather than swallowing a throw per element.
if (wantCss) {
    try { document.querySelector(wantCss); }
    catch (e) { return {elements: [], count: 0, described: [],
                        error: 'invalid css selector: ' + wantCss}; }
}

// name/role first, then css as an ADDITIONAL constraint — never instead of them.
const matches = [];
for (const el of scope.querySelectorAll('*')) {
    if (!visible(el)) continue;
    if (wantRole && roleOf(el) !== wantRole) continue;
    if (wantName && nameOf(el).toLowerCase() !== wantName) continue;
    if (wantCss  && !el.matches(wantCss)) continue;
    matches.push(el);
}

// An ancestor whose accessible name is computed from its contents also matches.
// Keep the innermost — that is the control, not its wrapper.
const innermost = matches.filter(el => !matches.some(o => o !== el && el.contains(o)));

return {
    elements: innermost,
    count: innermost.length,
    described: innermost.slice(0, 5).map(el => ({
        tag: el.tagName.toLowerCase(),
        role: roleOf(el),
        name: nameOf(el).slice(0, 60),
    })),
    error: null,
};
"""


def resolve(driver: WebDriver, target: Target) -> WebElement:
    """Return the one element this Target names, or raise."""
    matches, described = find_all(driver, target)

    if not matches:
        raise TargetNotFoundError(
            f"No accessible element matched {_describe(target)}. "
            f"If the control exists visually, it has no accessible name — "
            f"a screen reader user cannot identify it either (WCAG 4.1.2)."
        )

    # nth is the final narrowing operation, over the fully filtered list.
    if target.nth is not None:
        if target.nth >= len(matches):
            raise TargetNotFoundError(
                f"{_describe(target)} matched {len(matches)} element(s) after "
                f"filtering, but nth={target.nth} is out of range."
            )
        return matches[target.nth]

    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"{_describe(target)} matched {len(matches)} elements: {described}. "
            f"Add `role`, scope it with `within`, or add `css` as an extra "
            f"constraint. Avoid `nth` — DOM order changes with sorting and "
            f"pagination."
        )

    return matches[0]


def find_all(driver: WebDriver, target: Target):
    """Return (elements, descriptions) after within → name/role → css filtering.

    nth is NOT applied here — it is the final narrowing step, done in resolve()
    so it always indexes the fully filtered list.
    """
    inject_dom_a11y(driver)

    scope = None
    if target.within is not None:
        scope = resolve(driver, target.within)      # recursive; narrows the search

    result = driver.execute_script(
        _FIND,
        target.model_dump(exclude_none=True, include={"name", "role", "css"}),
        scope,
    )
    if result.get("error"):
        raise TargetNotFoundError(f"{_describe(target)}: {result['error']}")

    return result["elements"], result["described"]


def _describe(target: Target) -> str:
    bits = []
    if target.name:
        bits.append(f"name={target.name!r}")
    if target.role:
        bits.append(f"role={target.role!r}")
    if target.css:
        bits.append(f"css={target.css!r}")
    if target.within and target.within.name:
        bits.append(f"within={target.within.name!r}")
    return "Target(" + ", ".join(bits) + ")" if bits else "Target(empty)"

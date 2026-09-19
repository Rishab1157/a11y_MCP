"""Computes an accessibility tree from the DOM using dom-accessibility-api.

Firefox exposes no CDP equivalent of Accessibility.getFullAXTree, so this
models the spec rather than reading the browser's own tree. That is why
ax_source is "computed" — a consumer comparing findings across browsers
needs to know which side was ground truth.
"""
from selenium.webdriver.remote.webdriver import WebDriver

from Scan.AxTreeReader import AxTreeReader, register
from Scan.DomA11yLoader import BUNDLE_VERSION, inject_dom_a11y
from Scan.Dump import dump_json
from Scan.Roles import IGNORED_ROLES, INTERACTIVE_ROLES, NAME_REQUIRED_ROLES

# Tags that are never page content. <script> is the important one: its direct
# text is JavaScript source and would otherwise land in a "text" field.
SKIP_TAGS = {
    "html", "head", "script", "style", "meta", 
    "noscript", "template", "base", "title", "link",
}

_WALK = """
const skip = new Set(arguments[0]);
const api  = window.domA11y;
const out  = [];

// Direct text nodes only. textContent would give every ancestor the whole
// page's text and duplicate it at every level.
function directText(el) {
    let s = '';
    for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) s += node.nodeValue;
    }
    return s.replace(/\\s+/g, ' ').trim();
}

function focusable(el) {
    if (el.disabled) return false;
    if (el.hasAttribute('tabindex')) return parseInt(el.getAttribute('tabindex'), 10) >= 0;
    return ['a', 'button', 'input', 'select', 'textarea', 'summary']
        .includes(el.tagName.toLowerCase()) && (el.tagName !== 'A' || el.hasAttribute('href'));
}

function props(el) {
    const p = {};
    p.focusable = focusable(el);
    p.disabled  = api.isDisabled(el);
    if (el.required || el.getAttribute('aria-required') === 'true') p.required = true;
    if (el.checked !== undefined && el.type &&
        ['checkbox', 'radio'].includes(el.type)) p.checked = !!el.checked;
    else if (el.hasAttribute('aria-checked')) p.checked = el.getAttribute('aria-checked');
    if (el.hasAttribute('aria-expanded')) p.expanded = el.getAttribute('aria-expanded');
    if (el.hasAttribute('aria-selected')) p.selected = el.getAttribute('aria-selected');
    if (el.readOnly || el.getAttribute('aria-readonly') === 'true') p.readonly = true;
    if (el.hasAttribute('aria-invalid')) p.invalid = el.getAttribute('aria-invalid');
    const m = /^h([1-6])$/i.exec(el.tagName);
    if (m) p.level = parseInt(m[1], 10);
    else if (el.hasAttribute('aria-level')) p.level = parseInt(el.getAttribute('aria-level'), 10);
    return p;
}

// The document node, matching Chrome's RootWebArea -> document.
out.push({
    role: 'document',
    name: document.title || '',
    text: '',
    description: '',
    properties: {},
    inaccessible: false,
});

let index = 0;
for (const el of document.querySelectorAll('*')) {
    if (skip.has(el.tagName.toLowerCase())) continue;

    let role = null, name = '', description = '', inaccessible = false;
    try {
        role         = api.getRole(el);
        name         = api.computeAccessibleName(el) || '';
        description  = api.computeAccessibleDescription(el) || '';
        inaccessible = api.isInaccessible(el);
    } catch (e) {
        continue;                       // element the library cannot handle
    }

    out.push({
        node_index: index++,
        tag: el.tagName.toLowerCase(),
        role: role,                     // null for a plain div — normalised in Python
        name: String(name).trim(),
        text: directText(el),
        description: String(description).trim(),
        properties: props(el),
        inaccessible: inaccessible,
    });
}
return out;
"""

class FirefoxAxTreeReader(AxTreeReader):
    """Computes the tree from the DOM. Approximates the spec; not ground truth."""

    browser = "firefox"
    ax_source = "computed"
    ax_engine = "dom-accessibility-api"
    
    def read(self, driver: WebDriver) -> dict:
        inject_dom_a11y(driver)
        raw = driver.execute_script(_WALK, sorted(SKIP_TAGS))
        dump_json(raw, "ff_raw_nodes.json")
        
        nodes = []
        for item in raw:
            if item.get("inaccessible"):
                continue                       # Chrome's "ignored" equivalent

            # getRole returns null for a plain <div>; Chrome calls that generic.
            role = item.get("role") or "generic"
            text = item.get("text", "")

            # generic is noise unless it carries text of its own.
            if role in IGNORED_ROLES and not text:
                continue
            
            nodes.append({
                "node_id": item.get("node_index"),
                "backend_id": None,            # no CDP equivalent
                "role": role,
                "name": item.get("name", ""),
                "text": text,
                "description": item.get("description") or None,
                "properties": {k: v for k, v in (item.get("properties") or {}).items()
                               if v not in (False, None)},
                "interactive": role in INTERACTIVE_ROLES,
            })
            
        interactive = [n for n in nodes if n["interactive"]]
        
        result = {
            "ax_source": self.ax_source,
            "ax_engine": self.ax_engine,
            "ax_engine_version": BUNDLE_VERSION,
            "total_exposed": len(nodes),
            "interactive_count": len(interactive),
            "unnamed_interactive": [n for n in interactive if not n["name"]],
            "unnamed_required": [
                n for n in nodes
                if n["role"] in NAME_REQUIRED_ROLES and not n["name"]
            ],
            "dropped_text_count": 0,           # no StaticText folding on this path
            "roles_seen": sorted({n["role"] for n in nodes}),
            "nodes": nodes,
        }
        dump_json(result, "ff_result.json")
        return result
        
register(FirefoxAxTreeReader())
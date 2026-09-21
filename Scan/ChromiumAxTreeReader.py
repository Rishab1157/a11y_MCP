from selenium.webdriver.remote.webdriver import WebDriver

from Scan.AxTreeReader import AxTreeReader, register
from Scan.Dump import dump_json
from Scan.Roles import (
    CDP_TO_ARIA,
    DROPPED_ROLES,
    FOLDED_ROLES,
    IGNORED_ROLES,
    INTERACTIVE_ROLES,
    KEEP_PROPERTIES,
    NAME_REQUIRED_ROLES,
    HIDDEN_IGNORE_REASONS,
)

def _value(field) -> str:
    """CDP wraps every field as {"type": ..., "value": ...}."""
    if isinstance(field, dict):
        return field.get("value", "")
    return field or ""

def _hidden_ignore(node) -> bool:
    """True when a node is ignored because it is hidden, not merely uninteresting."""
    if not node.get("ignored"):
        return False
    reasons = {r.get("name") for r in (node.get("ignoredReasons") or [])}
    return bool(reasons & HIDDEN_IGNORE_REASONS)

class ChromiumAxTreeReader(AxTreeReader):
    """Reads Chrome's own accessibility tree over the DevTools Protocol.

    Ground truth — the exact structure the browser hands to assistive
    technology, not a re-implementation of the spec.
    """
    
    browser = "chrome"
    ax_source = "cdp"
    ax_engine = "chrome-devtools-protocol"
    
    def read(self, driver: WebDriver) -> dict:
        driver.execute_cdp_cmd("Accessibility.enable", {})
        raw = driver.execute_cdp_cmd("Accessibility.getFullAXTree", {})
        all_nodes = raw.get("nodes", [])
        dump_json(all_nodes, "ax_raw_nodes.json") 
        
        # ── PASS 1 ────────────────────────────────────────────────────────
        # Index every node by nodeId. Ignored nodes are included so that
        # parent lookups in pass 2 still resolve.
        by_id = {n.get("nodeId"): n for n in all_nodes}
        
        # ── PASS 2 ────────────────────────────────────────────────────────
        # Fold each StaticText onto the nearest ancestor that pass 3 will keep.
        # Chrome wraps text in nodes it marks ignored/"uninteresting", so the
        # text is usually a grandchild rather than a direct child — climbing
        # from the text is the only way to find its real owner.
        text_parts: dict[str, list[str]] = {}
        dropped_text = 0
        
        for node in all_nodes:
            
            if _value(node.get("role")) not in FOLDED_ROLES:
                continue
            
            if node.get("ignored"):
                dropped_text += 1                  # the text itself is hidden
                continue
            
            value = _value(node.get("name")).strip()
            if not value:
                continue
            
            # Climb to the first ancestor that survives pass 3.
            owner = by_id.get(node.get("parentId"))
            blocked = False
            while owner is not None and owner.get("ignored"):
                if _hidden_ignore(owner):
                    blocked = True                 # crossed something hidden
                    break
                owner = by_id.get(owner.get("parentId"))
                
            if blocked or owner is None:
                dropped_text += 1
                continue
            
            # The accessible name is computed from contents, so a control's
            # name usually already contains this string. Keep only what the
            # name does not already carry.
            owner_name = _value(owner.get("name")).strip()
            if value in owner_name:
                continue
            
            text_parts.setdefault(owner.get("nodeId"), []).append(value)
        
        text_by_parent = {k: " ".join(v) for k, v in text_parts.items()}

        # ── PASS 3 ────────────────────────────────────────────────────────
        # Emit normalised nodes.
        nodes = []
        for node in all_nodes:
            if node.get("ignored"):
                continue
            
            raw_role = _value(node.get("role"))
            if not raw_role:
                continue
            if raw_role in FOLDED_ROLES or raw_role in DROPPED_ROLES:
                continue
            
            # Normalise BEFORE filtering, so the filter speaks ARIA.
            role = CDP_TO_ARIA.get(raw_role, raw_role)
            text = text_by_parent.get(node.get("nodeId"), "")
            
            # generic is noise by default, but kept when it carries text of
            # its own — a wrapper div is noise, one holding "ALM CONNECTIONS"
            # is content.
            if role in IGNORED_ROLES and not text:
                continue
            
            props = {
                p["name"]: _value(p.get("value"))
                for p in node.get("properties", [])
                if p.get("name") in KEEP_PROPERTIES
            }
            
            nodes.append({
                "node_id": node.get("nodeId"),
                "backend_id": node.get("backendDOMNodeId"),
                "role": role,
                "name": _value(node.get("name")).strip(),
                "text": text,
                "description": _value(node.get("description")).strip() or None,
                "properties": props,
                "interactive": role in INTERACTIVE_ROLES,
            })
            
        interactive = [n for n in nodes if n["interactive"]]
        
        result = {
            "ax_source": self.ax_source,
            "ax_engine": self.ax_engine,
            "ax_engine_version": driver.capabilities.get("browserVersion", "unknown"),
            "total_exposed": len(nodes),
            "interactive_count": len(interactive),
            "unnamed_interactive": [n for n in interactive if not n["name"]],
            "unnamed_required": [
                n for n in nodes
                if n["role"] in NAME_REQUIRED_ROLES and not n["name"]
            ],
            "dropped_text_count": dropped_text,
            "roles_seen": sorted({n["role"] for n in nodes}),
            "nodes": nodes,
        }
        dump_json(result, "ax_result.json")
        return result
        
register(ChromiumAxTreeReader())


class EdgeAxTreeReader(ChromiumAxTreeReader):
    """Edge is Chromium, so its CDP tree is byte-identical in shape to Chrome's.

    Only the registry key differs — get_reader() looks readers up by the
    session's browser name.
    """

    browser = "edge"


register(EdgeAxTreeReader())
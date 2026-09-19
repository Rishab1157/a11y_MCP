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
)

def _value(field) -> str:
    """CDP wraps every field as {"type": ..., "value": ...}."""
    if isinstance(field, dict):
        return field.get("value", "")
    return field or ""

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
        # Fold StaticText children into their parent's "text".
        # Must run BEFORE any filtering: filter first and the parent is gone
        # before its text is ever read.
        text_by_parent: dict[str, str] = {}
        dropped_text = 0
        
        for node in all_nodes:
            
            if not (child_ids := node.get("childIds") or []):
                continue
            
            parent_ignored = node.get("ignored", False)
            parts = []
            
            for cid in child_ids:            # childIds order == reading order
                child = by_id.get(cid)
                if child is None:
                    continue
                if _value(child.get("role")) not in FOLDED_ROLES:
                    continue
                if child.get("ignored"):
                    dropped_text += 1        # hidden from AT, not reachable text
                    continue
                value = _value(child.get("name")).strip()
                if not value:
                    continue
                if parent_ignored:
                    dropped_text += 1        # owner not exposed; do not hoist
                    continue
                parts.append(value)
                
            if parts:
                text_by_parent[node.get("nodeId")] = " ".join(parts)

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
from selenium.webdriver.remote.webdriver import WebDriver

from Scan.AxTreeReader import AxTreeReader, register
from Scan.Roles import IGNORED_ROLES, INTERACTIVE_ROLES, KEEP_PROPERTIES, NAME_REQUIRED_ROLES


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
        
        nodes = []
        for node in raw.get("nodes", []):
            if node.get("ignored"):
                continue
            
            role = _value(node.get("role"))
            if not role or role in IGNORED_ROLES:
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
                "description": _value(node.get("description")).strip() or None,
                "properties": props,
                "interactive": role in INTERACTIVE_ROLES,
            })
            
        interactive = [n for n in nodes if n["interactive"]]
        unnamed_required = [
            n for n in nodes
            if n["role"] in NAME_REQUIRED_ROLES and not n["name"]
        ]

        return {
            "ax_source": self.ax_source,
            "ax_engine": self.ax_engine,
            "ax_engine_version": driver.capabilities.get("browserVersion", "unknown"),
            "total_exposed": len(nodes),
            "interactive_count": len(interactive),
            "unnamed_interactive": [n for n in interactive if not n["name"]],
            "unnamed_required": unnamed_required,
            "roles_seen": sorted({n["role"] for n in nodes}),
            "nodes": nodes,
        }

        
register(ChromiumAxTreeReader())
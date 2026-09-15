from fastmcp import FastMCP
from Session import SessionResult, registry
from Config.DriverConfig import AnyBrowserConfig, CromeConfig
from Config.DriverConfigBuilder import UnsupportedOptionError, get_builder

mcp = FastMCP("a11y MCP server")

@mcp.tool()
def create_driver(config: AnyBrowserConfig | None = None) -> dict:
    """Create a browser session for accessibility testing.

    Set "browser" to "chrome" or "firefox". Options differ per browser —
    Chrome supports zoom_percent, Firefox supports profile_path.
    Anything omitted uses the browser's default.

    Returns a session_id required by every other a11y tool.
    Always call close_session when the audit is finished.
    """
    
    registry.reap_idle()
    cfg = config or CromeConfig()
    
    try:
        builder = get_builder(cfg.browser)
        options = builder.build(cfg)
        driver = builder.create_driver(options)
    except (UnsupportedOptionError, ValueError) as e:
        return SessionResult.failure(str(e)).model_dump(exclude_none=True)
    except Exception as e:
        return SessionResult.failure(
            f"{cfg.browser} failed to start: {type(e).__name__}: {e}"
        ).model_dump(exclude_none=True)
        
    return SessionResult.created(registry.add(driver)).model_dump(exclude_none=True)


@mcp.tool()
def close_session(session_id: str) -> dict:
    """Close a browser session and free its process."""
    
    if registry.close(session_id):
        return {"ok": True, "closed": session_id}
    return SessionResult.failure(
        f"Unknown session_id: {session_id}"
    ).model_dump(exclude_none=True)
    
    
@mcp.tool()
def list_sessions() -> dict:
    """List how many browser sessions are currently open."""
    
    return {"ok": True, "open_sessions": len(registry)}

def main():
    mcp.run(transport = "streamable-http", host = "0.0.0.0", port = 8081)

if __name__ == "__main__":
    main()
from fastmcp import FastMCP

mcp = FastMCP("a11y MCP server")

@mcp.tool()
def crome_driver() -> str:
    """ this is the crome driver tool for the a11y """
    return "hi from crome driver"

def main():
    mcp.run(transport = "streamable-http", host = "0.0.0.0", port = 8081)

if __name__ == "__main__":
    main()
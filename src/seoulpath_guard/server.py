"""Composite MCP server entry point (skeleton)."""

from mcp.server.fastmcp import FastMCP

from seoulpath_guard.tools import definitions

mcp = FastMCP("seoulpath-guard")

# Tool registration: each tool is a thin wrapper that delegates to a module in
# seoulpath_guard.tools / qa / rebalance. Bodies are stubs for now.


@mcp.tool()
def search_places(query: str, area: str | None = None, category: str | None = None) -> dict:
    """Search candidate places via Kakao PlayMCP."""
    raise NotImplementedError


@mcp.tool()
def estimate_travel(origin: str, destination: str, mode: str = "transit") -> dict:
    """Estimate travel time between two stops via Kakao PlayMCP."""
    raise NotImplementedError


@mcp.tool()
def get_attraction_info(content_id: str) -> dict:
    """Get hours, closures, and fees from TourAPI."""
    raise NotImplementedError


@mcp.tool()
def search_events(date_from: str, date_to: str, area: str | None = None) -> dict:
    """Find festivals and events in a date window from TourAPI."""
    raise NotImplementedError


@mcp.tool()
def get_live_traffic(road_or_area: str) -> dict:
    """Get real-time road conditions from TOPIS."""
    raise NotImplementedError


@mcp.tool()
def qa_itinerary(itinerary: dict) -> dict:
    """Validate a full itinerary for feasibility and closures."""
    raise NotImplementedError


@mcp.tool()
def rebalance_itinerary(itinerary: dict, constraints: dict | None = None) -> dict:
    """Repair an itinerary given live changes."""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()

'''Composite MCP server entry point.'''

from datetime import date

from mcp.server.fastmcp import FastMCP

from seoulpath_guard.qa import checks as qa_checks
from seoulpath_guard.rebalance import engine as rebalance_engine
from seoulpath_guard.tools import barrier_free, cultural_events, seoul_rtd, topis, tourapi

mcp = FastMCP('seoulpath-guard')

# Tool registration: each tool is a thin wrapper that delegates to a module in
# seoulpath_guard.tools / qa / rebalance.


@mcp.tool()
def search_places(query: str, area: str | None = None, category: str | None = None) -> dict:
    '''Search candidate places via Kakao PlayMCP.'''
    raise NotImplementedError


@mcp.tool()
def estimate_travel(origin: str, destination: str, mode: str = 'transit') -> dict:
    '''Estimate travel time between two stops via Kakao PlayMCP.'''
    raise NotImplementedError


@mcp.tool()
def get_attraction_info(content_id: str) -> dict:
    '''Get hours, closures, and fees from TourAPI.'''
    raise NotImplementedError


@mcp.tool()
def parse_tourapi_hours(
    restdate: str | None = None,
    usetime: str | None = None,
    visit_date: str | None = None,
    visit_time: str | None = None,
) -> dict:
    '''Parse TourAPI restdate and usetime text. If visit_date (YYYY-MM-DD) and visit_time (HH:MM) are given, classify the visit as open, closed_day, outside_hours, after_last_entry, or unknown.'''
    return tourapi.evaluate_visit(restdate, usetime, visit_date, visit_time)


@mcp.tool()
def search_events(date_from: str, date_to: str, area: str | None = None) -> dict:
    '''Find festivals and events in a date window from TourAPI.'''
    raise NotImplementedError


@mcp.tool()
async def get_live_traffic(road_or_area: str) -> dict:
    '''Get TOPIS traffic incidents and a protest-related disruption flag for a road or area.'''
    return await topis.get_live_traffic(road_or_area)


@mcp.tool()
async def get_area_congestion(area_name: str) -> dict:
    '''Get Seoul Real-Time City Data population congestion level for an area (for example 명동 관광특구).'''
    return await seoul_rtd.get_area_congestion(area_name)


@mcp.tool()
async def check_barrier_free(content_id: str) -> dict:
    '''Check wheelchair, elevator, accessible restroom, and guide services for a venue via the KTO barrier-free API.'''
    return await barrier_free.check_barrier_free(content_id)


@mcp.tool()
async def get_idle_events(
    lat: float,
    lon: float,
    free_minutes: int,
    on_day: str | None = None,
    radius_km: float = 2.0,
) -> dict:
    '''Find Seoul cultural events running on a day (YYYY-MM-DD, default today) that can be reached and returned within free_minutes from a point.'''
    day = date.fromisoformat(on_day) if on_day else None
    return await cultural_events.get_idle_events(lat, lon, free_minutes, radius_km=radius_km, on_day=day)


@mcp.tool()
async def qa_itinerary(itinerary: dict, profile: dict | None = None) -> dict:
    '''Validate an itinerary: visit times vs hours and rest days, barrier-free access for profile needs (wheelchair, stroller, elderly), congestion and traffic per stop, and schedule gaps (idle slots over 90 minutes). Input: itinerary {date: YYYY-MM-DD, stops: [{name, content_id, area_name, road, arrive: HH:MM, stay_minutes, travel_minutes_from_prev, restdate, usetime, lat, lon}]}, profile {needs: [wheelchair|stroller|elderly]}. Returns status, failures, warnings, remediation, and idle slots.'''
    return await qa_checks.qa_itinerary(itinerary, profile)


@mcp.tool()
async def rebalance_itinerary(
    itinerary: dict,
    triggers: list[dict] | None = None,
    profile: dict | None = None,
    candidates: list[dict] | None = None,
) -> dict:
    '''Repair an itinerary given live triggers. Trigger types: closed_venue (stop_index or content_id, reason), congestion (stop_index, level), traffic_incident (road or stop_index), barrier_free_violation (stop_index, needs), idle_gap (injects free cultural events into idle slots). Substitutes come from candidates (same shape as stops). Returns the new itinerary, a change list with explanations, injected events, unresolved items, and a post-rebalance QA report.'''
    return await rebalance_engine.rebalance_itinerary(itinerary, triggers or [], profile or {}, candidates or [])


if __name__ == '__main__':
    mcp.run()

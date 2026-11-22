# seoulpath-guard

Composite MCP server for Seoul tourism itinerary QA and dynamic rebalancing.
Built for the STO Prompt-thon 2026.

SeoulPath Guard (서울패스 가드) validates a Seoul itinerary before the trip and rebalances it during the trip using live city data. See docs/PROPOSAL.md for the full proposal.

## Architecture

seoulpath-guard is a single MCP server that composes several public data sources into tools an AI agent can call:

- Kakao PlayMCP: place search, route and travel-time lookup, and map context.
- TourAPI / Seoul Public Data: attraction, event, opening-hours, and closure data.
- KTO barrier-free tourism API: accessibility flags for wheelchair, elevator, restroom, and guide services.
- Seoul cultural events API: events to fill idle time during a trip.
- TOPIS Live Data: real-time Seoul traffic incidents and protest-related disruptions.
- Seoul Real-Time City Data (SeoulRtd): population congestion by area.

```
Agent (MCP client)
   |
 seoulpath-guard (MCP server, src/seoulpath_guard/server.py)
   |-- src/seoulpath_guard/tools/kakao_playmcp.py   -> Kakao PlayMCP
   |-- src/seoulpath_guard/tools/tourapi.py         -> TourAPI hours and rest-day parser
   |-- src/seoulpath_guard/tools/barrier_free.py    -> KTO barrier-free API
   |-- src/seoulpath_guard/tools/cultural_events.py -> Seoul cultural events API
   |-- src/seoulpath_guard/tools/topis.py           -> TOPIS incidents and protest check
   |-- src/seoulpath_guard/tools/seoul_rtd.py       -> Seoul Real-Time City Data congestion
   |-- src/seoulpath_guard/qa/                      -> itinerary QA rules
   |-- src/seoulpath_guard/rebalance/               -> dynamic rebalancing logic
```

## Track 2 context

Track 2 of the Prompt-thon focuses on itinerary quality assurance and live adjustment. Goals:

- Detect infeasible itineraries (time conflicts, closed venues, unrealistic travel times).
- Suggest or apply rebalancing when live conditions change.
- Keep every recommendation traceable to a data source.

## Tools

| Tool | Purpose | Key inputs | Source | Status |
|---|---|---|---|---|
| `search_places` | Find candidate places | `query`, `area`, `category` | Kakao PlayMCP | Stub |
| `estimate_travel` | Travel time between stops | `origin`, `destination`, `mode` | Kakao PlayMCP | Stub |
| `get_attraction_info` | Hours, closures, fees | `content_id` | TourAPI | Stub |
| `parse_tourapi_hours` | Parse restdate and usetime, evaluate a visit | `restdate`, `usetime`, `visit_date`, `visit_time` | TourAPI text | Implemented |
| `search_events` | Festivals and events in window | `date_from`, `date_to`, `area` | TourAPI | Stub |
| `get_live_traffic` | Incidents and protest check on a road or area | `road_or_area` | TOPIS | Implemented |
| `get_area_congestion` | Population congestion level | `area_name` | Seoul Real-Time City Data | Implemented |
| `check_barrier_free` | Accessibility flags for a venue | `content_id` | KTO barrier-free API | Implemented |
| `get_idle_events` | Events that fit an idle window | `lat`, `lon`, `free_minutes`, `on_day`, `radius_km` | Seoul cultural events | Implemented |
| `qa_itinerary` | Validate a full itinerary | `itinerary` (JSON) | Composite | Stub |
| `rebalance_itinerary` | Repair an itinerary given changes | `itinerary`, `constraints` | Composite | Stub |

See src/seoulpath_guard/tools/definitions.py for the machine-readable schema.

## Setup

Requirements: Python 3.11+.

```bash
git clone https://github.com/devchun01/seoulpath-guard.git
cd seoulpath-guard
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # then fill in your API keys
python -m seoulpath_guard.server
```

API keys needed: Kakao REST API key (PlayMCP), TourAPI service key (data.go.kr, also used for the KTO barrier-free API), Seoul Open Data Plaza key (cultural events, TOPIS, SeoulRtd).

## Status

Core clients are implemented. Endpoint paths and field names for the KTO barrier-free, Seoul cultural events, TOPIS, and SeoulRtd services follow the public documentation patterns and must be verified with live keys. Kakao PlayMCP, search_events, get_attraction_info, qa_itinerary, and rebalance_itinerary are still stubs that raise NotImplementedError.

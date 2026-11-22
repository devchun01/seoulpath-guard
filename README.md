# seoulpath-guard

Composite MCP server for Seoul tourism itinerary QA and dynamic rebalancing.
Built for the Seoul Tourism Prompt-thon 2026.

## Architecture

seoulpath-guard is a single MCP server that composes three upstream data sources into tools an AI agent can call:

- Kakao PlayMCP: place search, route and travel-time lookup, and map context.
- TourAPI / Seoul Public Data: attraction, event, opening-hours, and closure data.
- TOPIS Live Data: real-time Seoul traffic and road conditions.

The server validates a draft itinerary (QA) and rebalances it when conditions change (for example a closure, a rain alert, or congestion).

```
Agent (MCP client)
   |
 seoulpath-guard (MCP server)
   |-- src/tools/kakao_playmcp.py   -> Kakao PlayMCP
   |-- src/tools/tourapi.py         -> TourAPI / Seoul Public Data
   |-- src/tools/topis.py           -> TOPIS Live Data
   |-- src/qa/                      -> itinerary QA rules
   |-- src/rebalance/               -> dynamic rebalancing logic
```

## Track 2 context

Track 2 of the Prompt-thon focuses on itinerary quality assurance and live adjustment. Goals:

- Detect infeasible itineraries (time conflicts, closed venues, unrealistic travel times).
- Suggest or apply rebalancing when live conditions change.
- Keep every recommendation traceable to a data source.

## Tools schema (planned)

| Tool | Purpose | Key inputs | Source |
|---|---|---|---|
| `search_places` | Find candidate places | `query`, `area`, `category` | Kakao PlayMCP |
| `estimate_travel` | Travel time between stops | `from`, `to`, `mode` | Kakao PlayMCP |
| `get_attraction_info` | Hours, closures, fees | `content_id` | TourAPI |
| `search_events` | Festivals and events in window | `date_from`, `date_to`, `area` | TourAPI |
| `get_live_traffic` | Real-time road conditions | `road_or_area` | TOPIS |
| `qa_itinerary` | Validate a full itinerary | `itinerary` (JSON) | Composite |
| `rebalance_itinerary` | Repair an itinerary given changes | `itinerary`, `constraints` | Composite |

See src/tools/definitions.py for the machine-readable schema.

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

API keys needed: Kakao REST API key (PlayMCP), TourAPI service key (data.go.kr), TOPIS / Seoul Open Data key.

## Status

Skeleton only. Tool bodies are stubs that raise NotImplementedError until implemented.

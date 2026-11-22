# SeoulPath Guard (서울패스 가드)

실시간 도시 데이터 기반의 적응형 서울 관광 일정 QA 및 동적 리밸런싱 Composite MCP 서버

Built for the STO Prompt-thon 2026.

## 1. Project Title

SeoulPath Guard (서울패스 가드)

A composite MCP server that (a) validates a Seoul tourist itinerary before the trip and (b) rebalances it during the trip using live city data.

## 2. Problem Statement and Background

Tourists who plan a Seoul itinerary from static guides run into four recurring failures:

1. Unpredictable transit. Subway and bus disruptions, road incidents, and sudden closures break a planned route with no warning.
2. Mobility barriers. Travelers using wheelchairs, strollers, or who are visually or hearing impaired cannot easily tell whether a venue has elevators, accessible restrooms, or guide services. Most itinerary tools ignore this.
3. Empty schedule gaps. When a venue closes early, a stop is cancelled, or a visit finishes ahead of schedule, the resulting idle hour is wasted instead of filled with a nearby cultural event.
4. Crowded spots. Popular districts can reach capacity at peak hours, and the traveler finds out only on arrival.

Seoul already publishes the data needed to address these: TourAPI (business hours and rest days), the KTO barrier-free tourism API, the Seoul cultural events API, TOPIS live traffic and incident data, Seoul Real-Time City Data (SeoulRtd) population congestion, and Odii audio guides. The gap is a single agent-facing layer that combines them and checks an itinerary against them.

## 3. Core Architecture

```
Agent (MCP client)
   |
seoulpath-guard (composite MCP server, src/seoulpath_guard/server.py)
   |-- Static pre-trip QA
   |     |-- tools/tourapi.py          restdate / usetime parsing and visit-time checks
   |     |-- tools/kakao_playmcp.py    place search and travel time (PlayMCP)
   |     |-- qa/                       itinerary feasibility rules
   |-- Dynamic mid-trip rebalancing
   |     |-- tools/topis.py            TOPIS traffic incidents and protest check
   |     |-- tools/seoul_rtd.py        SeoulRtd population congestion by area
   |     |-- rebalance/                repair logic
   |-- Killer features
         |-- tools/barrier_free.py     KTO barrier-free accessibility filter
         |-- tools/cultural_events.py  idle-time cultural event injection
         |-- (planned) storytelling and night safety (Odii, night living population)
```

### 3.1 Static Pre-trip QA

Before the trip, each stop in a draft itinerary is checked against:

- TourAPI business hours (usetime) and rest days (restdate). Free-text fields such as '매주 월요일 휴무' or '09:00~18:00 (입장마감 17:00)' are parsed into structured rules. A visit at a given date and time is then classified as open, closed_day, outside_hours, after_last_entry, or unknown.
- Kakao PlayMCP for place identity and travel time between stops, so unrealistic transfers are flagged.

### 3.2 Dynamic Mid-trip Rebalancing

During the trip the agent re-checks the remaining stops:

- TOPIS incidents and protest-related disruptions on the route or in the area.
- SeoulRtd congestion level for each hotspot (여유, 보통, 약간 붐빔, 붐빔). A stop at 약간 붐빔 or above is a candidate for rescheduling.
- When a stop is dropped or finished early, the idle-time injection feature proposes nearby events.

## 4. Killer Features (from ideation)

### a) Barrier-Free Smart Filter

Integrates the Korea Tourism Organization barrier-free tourism API (한국관광공사 무장애 여행 API). For each venue the server returns normalized flags for wheelchair access, elevator, accessible restroom, tactile guide, audio guide for visually impaired visitors, help dog policy, and stroller friendliness. Unknown values are reported as unknown rather than guessed. The itinerary can then be filtered by traveler needs.

Implemented in: src/seoulpath_guard/tools/barrier_free.py (tool: check_barrier_free).

### b) Idle-Time Event Injection

Uses the Seoul cultural events API (서울시 문화행사 정보). When a gap of N minutes appears, the server finds events that are running on the given day, lie within a radius of the traveler, and can be reached and returned within the gap (round-trip walking estimate). Results are sorted by distance.

Implemented in: src/seoulpath_guard/tools/cultural_events.py (tool: get_idle_events).

### c) Multilingual Storytelling and Night Safety

- Odii audio guide integration provides multilingual storytelling for each stop, so the same itinerary can be narrated in the traveler's language.
- Night safety uses the nighttime living population data from Seoul open data. Areas with low nighttime population or recent incidents are flagged for evening stops.

Status: planned. Not yet implemented.

## 5. Tool Inventory

| Tool | Module | Purpose | Upstream | Status |
|---|---|---|---|---|
| search_places | kakao_playmcp.py | Find candidate places | Kakao PlayMCP | Stub |
| estimate_travel | kakao_playmcp.py | Travel time between stops | Kakao PlayMCP | Stub |
| get_attraction_info | tourapi.py | Hours, closures, fees | TourAPI | Stub |
| parse_tourapi_hours | tourapi.py | Parse restdate and usetime, evaluate a visit | TourAPI text | Implemented |
| search_events | tourapi.py | Events in a date window | TourAPI | Stub |
| get_live_traffic | topis.py | Incidents and protest check | TOPIS via Seoul open data | Implemented |
| get_area_congestion | seoul_rtd.py | Population congestion for an area | SeoulRtd | Implemented |
| check_barrier_free | barrier_free.py | Accessibility flags | KTO barrier-free API | Implemented |
| get_idle_events | cultural_events.py | Events that fit an idle window | Seoul cultural events API | Implemented |
| qa_itinerary | server | Full itinerary validation | Composite | Stub |
| rebalance_itinerary | server | Repair an itinerary | Composite | Stub |

## 6. Data Sources and Keys

- TourAPI and data.go.kr services (including KTO barrier-free): TOURAPI_SERVICE_KEY
- Seoul Open Data Plaza (cultural events, TOPIS, SeoulRtd): SEOUL_OPEN_DATA_KEY
- Kakao REST API (PlayMCP): KAKAO_REST_API_KEY

See .env.example. Keys are read from the environment only and are never committed.

## 7. Roadmap

1. Milestone 1 (this commit): planning document, the five core upstream clients, and the TourAPI hours parser registered as an MCP tool.
2. Milestone 2: qa_itinerary composes the static checks (hours, rest days, travel time from PlayMCP, barrier-free needs) into a per-stop report with source references.
3. Milestone 3: rebalance_itinerary uses TOPIS, SeoulRtd, and idle-time event injection to propose a repaired schedule.
4. Milestone 4: Odii storytelling and night safety features, then an end-to-end demo itinerary.

## 8. Risks and Mitigations

- Upstream endpoint and field names. Some endpoints (KTO barrier-free detail, TOPIS incident service) are configured by constant or environment variable and must be verified against live API documentation. Mitigation: each client raises a clear error on unexpected responses, and nothing is guessed.
- Free-text hours and rest days are inconsistent. Mitigation: the parser returns unknown when it cannot interpret a field, and the QA report says so. Holidays such as 설날 and 추석 are detected as text but not computed.
- TOPIS coordinates use GRS80 TM. Mitigation: incidents are matched by road name or keyword, and the coordinate conversion is noted as a limitation.
- Rate limits and availability of public APIs. Mitigation: short timeouts and no retries on mutating paths. Caching is a planned improvement.

## 9. Evaluation Criteria Alignment (STO Prompt-thon 2026)

### Understanding (30)

The problem statement covers the four failures a Seoul tourist actually meets (transit disruption, mobility barriers, idle gaps, crowding). Each is tied to a specific public data source and a specific tool.

### Feasibility (30)

All upstream sources are public Korean open-data APIs. The core clients and the hours parser are implemented as MCP tools and are unit-testable without live keys. Milestones are ordered so that the static QA path works before the dynamic path depends on it.

### Creativity (20)

The three killer features combine data that is normally used separately: accessibility data for filtering, cultural event data to fill idle time, and congestion data to trigger rebalancing. Night safety and storytelling extend the same itinerary into the evening and across languages.

### Acquisition Value (20)

The project shows how Korean public data (TourAPI, KTO, Seoul Open Data, TOPIS, SeoulRtd) can be turned into agent-usable tools, which is a reusable pattern for other cities and tourism operators. The code, the parsing rules, and the milestone plan are published in the repository.

## 10. Current Status and Limitations

- Implemented: the parser for TourAPI restdate and usetime text, and the clients for KTO barrier-free, Seoul cultural events, TOPIS incidents, and SeoulRtd congestion.
- Not yet verified against live APIs. Endpoint paths and field names are based on the public documentation patterns and must be confirmed with a real key before production use.
- Kakao PlayMCP, TourAPI search_events, get_attraction_info, qa_itinerary, and rebalance_itinerary remain stubs.

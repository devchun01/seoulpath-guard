"""Machine-readable tool definitions for the composite server.

Each entry documents one MCP tool and its upstream source.
"""

TOOL_DEFINITIONS = [
    {
        "name": "search_places",
        "source": "Kakao PlayMCP",
        "inputs": {"query": "str", "area": "str | None", "category": "str | None"},
    },
    {
        "name": "estimate_travel",
        "source": "Kakao PlayMCP",
        "inputs": {"origin": "str", "destination": "str", "mode": "str = transit"},
    },
    {
        "name": "get_attraction_info",
        "source": "TourAPI / Seoul Public Data",
        "inputs": {"content_id": "str"},
    },
    {
        "name": "search_events",
        "source": "TourAPI / Seoul Public Data",
        "inputs": {"date_from": "str", "date_to": "str", "area": "str | None"},
    },
    {
        "name": "get_live_traffic",
        "source": "TOPIS Live Data",
        "inputs": {"road_or_area": "str"},
    },
    {
        "name": "qa_itinerary",
        "source": "Composite",
        "inputs": {"itinerary": "dict"},
    },
    {
        "name": "rebalance_itinerary",
        "source": "Composite",
        "inputs": {"itinerary": "dict", "constraints": "dict | None"},
    },
]

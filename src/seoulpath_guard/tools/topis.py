'''TOPIS (Seoul Transport Operation Information Service) incident and protest check.

Uses the Seoul Open Data incident service AccInfo by default. The service name and
field names are configurable and must be verified against the live API documentation.
Incident coordinates are GRS80 TM and are not converted here; matching is by road
name and keyword.
'''

from __future__ import annotations

import os
from typing import Any

from seoulpath_guard.tools._http import get_json, require_env

BASE_URL = os.getenv('SEOUL_OPEN_API_BASE', 'http://openapi.seoul.go.kr:8088')
SERVICE = os.getenv('TOPIS_INCIDENT_SERVICE', 'AccInfo')
PAGE_SIZE = 1000
MAX_RESULTS = 20
PROTEST_KEYWORDS = ('집회', '시위', '행진')


async def fetch_incidents() -> list[dict[str, Any]]:
    key = require_env('SEOUL_OPEN_DATA_KEY')
    payload = await get_json(f'{BASE_URL}/{key}/json/{SERVICE}/1/{PAGE_SIZE}/')
    service = payload.get(SERVICE)
    if not isinstance(service, dict):
        raise RuntimeError(f'Unexpected response from TOPIS service {SERVICE}: {str(payload)[:200]}')
    result = service.get('RESULT', {}) or {}
    code = result.get('CODE')
    if code and code != 'INFO-000':
        raise RuntimeError(f"TOPIS API error {code}: {result.get('MESSAGE')}")
    rows = service.get('row', []) or []
    return [row for row in rows if isinstance(row, dict)]


def is_protest_related(row: dict[str, Any]) -> bool:
    text = ' '.join(str(row.get(field, '')) for field in ('acc_type', 'acc_dtype', 'acc_info'))
    return any(keyword in text for keyword in PROTEST_KEYWORDS)


def matches_query(row: dict[str, Any], query: str) -> bool:
    text = ' '.join(str(row.get(field, '')) for field in ('road_nm', 'acc_info', 'link_id'))
    tokens = [token for token in query.split() if token]
    return bool(tokens) and any(token in text for token in tokens)


async def get_live_traffic(road_or_area: str) -> dict[str, Any]:
    rows = await fetch_incidents()
    matched = [row for row in rows if matches_query(row, road_or_area)]
    incidents = [
        {
            'road': row.get('road_nm'),
            'type': row.get('acc_type'),
            'detail': row.get('acc_info'),
            'occurred': row.get('occr_date'),
            'expected_clear': row.get('exp_clr_date'),
            'is_protest_related': is_protest_related(row),
        }
        for row in matched[:MAX_RESULTS]
    ]
    protest_count = sum(1 for item in incidents if item['is_protest_related'])
    return {
        'query': road_or_area,
        'incident_count': len(matched),
        'protest_related_count': protest_count,
        'protest_flag': protest_count > 0,
        'incidents': incidents,
        'coordinate_note': 'Incident coordinates are GRS80 TM and were not converted; matching uses road name and keywords.',
        'source': f'TOPIS via Seoul Open Data ({SERVICE})',
    }

'''Seoul cultural events client (Seoul Open Data culturalEventInfo) and idle-time injection.'''

from __future__ import annotations

import math
import os
from datetime import date
from typing import Any

from seoulpath_guard.tools._http import get_json, require_env

BASE_URL = os.getenv('SEOUL_OPEN_API_BASE', 'http://openapi.seoul.go.kr:8088')
SERVICE = 'culturalEventInfo'
PAGE_SIZE = 1000
WALK_SPEED_KMH = 4.5
SUCCESS_CODE = 'INFO-000'


async def fetch_events() -> list[dict[str, Any]]:
    key = require_env('SEOUL_OPEN_DATA_KEY')
    payload = await get_json(f'{BASE_URL}/{key}/json/{SERVICE}/1/{PAGE_SIZE}/')
    service = payload.get(SERVICE)
    if not isinstance(service, dict):
        raise RuntimeError(f'Unexpected response from {SERVICE}: {str(payload)[:200]}')
    result = service.get('RESULT', {}) or {}
    code = result.get('CODE')
    if code and code != SUCCESS_CODE:
        raise RuntimeError(f"Seoul cultural events API error {code}: {result.get('MESSAGE')}")
    rows = service.get('row', []) or []
    return [row for row in rows if isinstance(row, dict)]


def _parse_day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def is_running_on(row: dict[str, Any], day: date) -> bool:
    start = _parse_day(row.get('START_DATE'))
    end = _parse_day(row.get('END_DATE'))
    if start is None or end is None:
        return False
    return start <= day <= end


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def find_idle_events(
    events: list[dict[str, Any]],
    lat: float,
    lon: float,
    on_day: date,
    free_minutes: int,
    radius_km: float = 2.0,
    limit: int = 5,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in events:
        if not is_running_on(row, on_day):
            continue
        try:
            event_lat = float(row.get('LAT'))
            event_lon = float(row.get('LOT'))
        except (TypeError, ValueError):
            continue
        distance = haversine_km(lat, lon, event_lat, event_lon)
        if distance > radius_km:
            continue
        round_trip_minutes = 2 * distance / WALK_SPEED_KMH * 60
        if round_trip_minutes > free_minutes:
            continue
        candidates.append({
            'title': row.get('TITLE'),
            'place': row.get('PLACE'),
            'start_date': str(row.get('START_DATE', ''))[:10],
            'end_date': str(row.get('END_DATE', ''))[:10],
            'is_free': row.get('IS_FREE'),
            'fee': row.get('USE_FEE'),
            'url': row.get('ORG_LINK'),
            'distance_km': round(distance, 2),
            'round_trip_walk_minutes': round(round_trip_minutes),
        })
    candidates.sort(key=lambda item: item['distance_km'])
    return candidates[:limit]


async def get_idle_events(
    lat: float,
    lon: float,
    free_minutes: int,
    radius_km: float = 2.0,
    on_day: date | None = None,
) -> dict[str, Any]:
    day = on_day or date.today()
    events = await fetch_events()
    matches = find_idle_events(events, lat, lon, day, free_minutes, radius_km)
    return {
        'on_day': day.isoformat(),
        'free_minutes': free_minutes,
        'radius_km': radius_km,
        'event_count': len(matches),
        'events': matches,
        'source': 'Seoul cultural events API (culturalEventInfo)',
    }

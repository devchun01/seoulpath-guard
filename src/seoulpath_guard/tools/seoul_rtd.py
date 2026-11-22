'''Seoul Real-Time City Data (SeoulRtd, service citydata) congestion client.'''

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from seoulpath_guard.tools._http import as_list, get_json, require_env

BASE_URL = os.getenv('SEOUL_OPEN_API_BASE', 'http://openapi.seoul.go.kr:8088')
SERVICE = 'citydata'
CONGESTION_RANK = {'여유': 1, '보통': 2, '약간 붐빔': 3, '붐빔': 4}
REBALANCE_RANK = 3


async def get_area_congestion(area_name: str) -> dict[str, Any]:
    key = require_env('SEOUL_OPEN_DATA_KEY')
    url = f'{BASE_URL}/{key}/json/{SERVICE}/1/5/{quote(area_name)}'
    payload = await get_json(url)
    city = payload.get('CITYDATA')
    if not isinstance(city, dict):
        result = payload.get('RESULT', {}) or {}
        raise RuntimeError(f"SeoulRtd error for '{area_name}': {result.get('MESSAGE', str(payload)[:200])}")
    rows = as_list(city.get('LIVE_PPLTN_STTS'))
    if not rows or not isinstance(rows[0], dict):
        raise RuntimeError(f"No live population data returned for '{area_name}'")
    row = rows[0]
    level = row.get('AREA_CONGEST_LVL')
    rank = CONGESTION_RANK.get(str(level).strip())
    return {
        'area': area_name,
        'congestion_level': level,
        'congestion_rank': rank,
        'population_min': row.get('AREA_PPLTN_MIN'),
        'population_max': row.get('AREA_PPLTN_MAX'),
        'observed_at': row.get('PPLTN_TIME'),
        'should_rebalance': rank is not None and rank >= REBALANCE_RANK,
        'source': 'Seoul Real-Time City Data (SeoulRtd)',
    }

'''KTO barrier-free tourism (무장애 여행) client and accessibility check.

Endpoint and field names follow the KTO KorWithService family on data.go.kr.
The base URL and detail endpoint can be overridden by environment variables.
Verify them against the live API documentation before production use.
'''

from __future__ import annotations

import os
from typing import Any

from seoulpath_guard.tools._http import as_list, get_json, require_env

BASE_URL = os.getenv('KTO_BARRIER_FREE_BASE_URL', 'https://apis.data.go.kr/B551011/KorWithService2')
DETAIL_ENDPOINT = os.getenv('KTO_BARRIER_FREE_DETAIL_ENDPOINT', 'detailWithTour2')

# Normalized feature name -> candidate upstream field names (first non-empty wins).
FEATURE_FIELDS: dict[str, tuple[str, ...]] = {
    'wheelchair_access': ('wchairAcces', 'wchairAccesInfo'),
    'elevator': ('elevator', 'elevatorInfo'),
    'accessible_restroom': ('wchairToilet', 'restroom'),
    'tactile_guide': ('braileBlock', 'braileBlockInfo'),
    'audio_guide_for_visually_impaired': ('audioGuide', 'audioGuideInfo'),
    'help_dog_allowed': ('helpDog', 'helpDogInfo'),
    'stroller_friendly': ('stroller', 'strollerInfo'),
}

NEGATIVE_MARKERS = ('없음', '불가', '미제공', '해당없음')
NEGATIVE_VALUES = {'n', 'no', '0', 'false'}


def _unwrap_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get('response', {})
    header = response.get('header', {})
    code = str(header.get('resultCode', '0000'))
    if code != '0000':
        raise RuntimeError(f"KTO barrier-free API error {code}: {header.get('resultMsg', 'unknown')}")
    items = response.get('body', {}).get('items', {})
    if not isinstance(items, dict):
        return []
    return [row for row in as_list(items.get('item')) if isinstance(row, dict)]


def _to_flag(value: Any) -> bool:
    text = str(value).strip()
    if text.lower() in NEGATIVE_VALUES or any(marker in text for marker in NEGATIVE_MARKERS):
        return False
    return True


def normalize_features(row: dict[str, Any]) -> dict[str, bool | None]:
    features: dict[str, bool | None] = {}
    for feature, fields in FEATURE_FIELDS.items():
        raw = next((row.get(name) for name in fields if row.get(name) not in (None, '')), None)
        features[feature] = None if raw is None else _to_flag(raw)
    return features


async def fetch_accessibility_rows(content_id: str) -> list[dict[str, Any]]:
    key = require_env('TOURAPI_SERVICE_KEY')
    params = {
        'serviceKey': key,
        'MobileOS': 'ETC',
        'MobileApp': 'SeoulPathGuard',
        '_type': 'json',
        'contentId': content_id,
    }
    payload = await get_json(f'{BASE_URL}/{DETAIL_ENDPOINT}', params)
    return _unwrap_items(payload)


async def check_barrier_free(content_id: str) -> dict[str, Any]:
    rows = await fetch_accessibility_rows(content_id)
    if not rows:
        return {
            'content_id': content_id,
            'found': False,
            'features': {},
            'unknown_features': list(FEATURE_FIELDS),
            'summary': 'No barrier-free record found for this venue.',
            'source': 'KTO barrier-free API',
        }
    features = normalize_features(rows[0])
    positive = [name for name, value in features.items() if value is True]
    unknown = [name for name, value in features.items() if value is None]
    summary = 'Confirmed: ' + ', '.join(positive) if positive else 'No confirmed barrier-free features.'
    return {
        'content_id': content_id,
        'found': True,
        'features': features,
        'unknown_features': unknown,
        'summary': summary,
        'source': 'KTO barrier-free API',
    }

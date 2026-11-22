'''Shared HTTP helpers for Korean open-data APIs.'''

from __future__ import annotations

import os
from typing import Any

import httpx

TIMEOUT_SECONDS = 10.0


def require_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing environment variable: {name}')
    return value


async def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def as_list(value: Any) -> list[Any]:
    if value is None or value == '':
        return []
    return value if isinstance(value, list) else [value]

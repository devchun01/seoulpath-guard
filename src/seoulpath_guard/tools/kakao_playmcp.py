"""Kakao PlayMCP client (skeleton)."""


async def search_places(query: str, area: str | None = None, category: str | None = None) -> dict:
    raise NotImplementedError


async def estimate_travel(origin: str, destination: str, mode: str = "transit") -> dict:
    raise NotImplementedError

"""TourAPI / Seoul Public Data client (skeleton)."""


async def get_attraction_info(content_id: str) -> dict:
    raise NotImplementedError


async def search_events(date_from: str, date_to: str, area: str | None = None) -> dict:
    raise NotImplementedError

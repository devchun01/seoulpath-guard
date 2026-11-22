'''Itinerary QA checks.

Each stop is checked for temporal validity, barrier-free access (when the profile needs it),
congestion, and traffic incidents. Gaps between consecutive stops are checked for overlaps
and idle slots. External lookups go through Deps so the logic can be tested offline. A failed
lookup is reported as a warning rather than passed silently.
'''

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from seoulpath_guard.tools import barrier_free, seoul_rtd, topis, tourapi

IDLE_GAP_THRESHOLD_MINUTES = 90
CONGESTION_WARN_RANK = 3  # 약간 붐빔 and above
DEFAULT_STAY_MINUTES = 60

# Profile need -> normalized barrier-free features that must be confirmed.
# Ramp and barrier-free access are represented by wheelchair_access in the KTO client.
ACCESSIBILITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    'wheelchair': ('wheelchair_access', 'elevator', 'accessible_restroom'),
    'stroller': ('stroller_friendly', 'elevator'),
    'elderly': ('elevator', 'accessible_restroom'),
}

_STATUS_RANK = {'skipped': 0, 'pass': 1, 'warn': 2, 'fail': 3}

REMEDIATION_BY_STATUS = {
    'closed_day': 'Move this visit to another day or choose an open venue.',
    'outside_hours': 'Move the arrival time inside opening hours.',
    'after_last_entry': 'Arrive before the last entry time.',
}


@dataclass
class Deps:
    get_barrier_free: Callable[[str], Awaitable[dict[str, Any]]] = barrier_free.check_barrier_free
    get_congestion: Callable[[str], Awaitable[dict[str, Any]]] = seoul_rtd.get_area_congestion
    get_traffic: Callable[[str], Awaitable[dict[str, Any]]] = topis.get_live_traffic


def to_minutes(hhmm: str) -> int:
    hour, minute = str(hhmm).split(':')[:2]
    return int(hour) * 60 + int(minute)


def format_minutes(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def stay_minutes(stop: dict[str, Any]) -> int:
    value = stop.get('stay_minutes')
    return int(value) if value is not None else DEFAULT_STAY_MINUTES


def required_features(profile: dict[str, Any] | None) -> list[str]:
    required: list[str] = []
    for need in (profile or {}).get('needs') or []:
        for feature in ACCESSIBILITY_REQUIREMENTS.get(str(need).lower(), ()):
            if feature not in required:
                required.append(feature)
    return required


def _result(status: str, detail: str, remediation: str | None = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {'status': status, 'detail': detail, 'remediation': remediation}
    result.update(extra)
    return result


def _overall(statuses: list[str]) -> str:
    worst = max(statuses, key=lambda status: _STATUS_RANK.get(status, 0), default='skipped')
    return 'pass' if worst == 'skipped' else worst


def check_temporal(stop: dict[str, Any], day: str | None) -> dict[str, Any]:
    arrive = stop.get('arrive')
    if not arrive:
        return _result('fail', 'Missing arrival time.', 'Add an arrival time (HH:MM) for this stop.')
    if not day:
        return _result('warn', 'No itinerary date; hours and rest-day checks were skipped.',
                       'Add the visit date (YYYY-MM-DD).')
    try:
        evaluation = tourapi.evaluate_visit(stop.get('restdate'), stop.get('usetime'), day, arrive)
    except ValueError as exc:
        return _result('fail', f'Invalid date or time: {exc}',
                       'Use YYYY-MM-DD for the date and HH:MM for times.')
    status = evaluation['status']
    if status == 'open':
        result = _result('pass', evaluation['reason'])
        usetime = evaluation['usetime']
        close = usetime.get('close')
        if close and not usetime['is_24h'] and not usetime['overnight']:
            depart = to_minutes(arrive) + stay_minutes(stop)
            if depart > to_minutes(close):
                result.update(
                    status='warn',
                    detail=f'Planned stay ends at {format_minutes(depart)}, after closing at {close}.',
                    remediation='Shorten the stay or arrive earlier.',
                )
        return result
    if status == 'unknown':
        return _result('warn', evaluation['reason'],
                       'Confirm hours and rest days on the venue page; the TourAPI text could not be parsed.')
    return _result('fail', evaluation['reason'], REMEDIATION_BY_STATUS.get(status, 'Adjust the visit time or date.'))


async def check_accessibility(stop: dict[str, Any], required: list[str], deps: Deps) -> dict[str, Any]:
    if not required:
        return _result('skipped', 'No accessibility needs in profile.')
    cid = stop.get('content_id')
    if not cid:
        return _result('warn', 'No content_id; barrier-free access was not verified.',
                       'Add the TourAPI content_id for this venue.')
    try:
        record = await deps.get_barrier_free(str(cid))
    except Exception as exc:
        return _result('warn', f'Barrier-free lookup failed: {exc}',
                       'Verify step-free access and accessible restrooms directly with the venue.')
    if not record.get('found'):
        return _result('warn', 'No barrier-free record for this venue.',
                       'Verify ramp, elevator, and accessible restroom access with the venue before visiting.')
    features = record.get('features', {})
    missing = [feature for feature in required if features.get(feature) is False]
    unknown = [feature for feature in required if features.get(feature) is None]
    if missing:
        return _result('fail', 'Does not meet accessibility needs: ' + ', '.join(missing),
                       'Swap this venue for an accessible alternative (rebalance_itinerary with a barrier_free_violation trigger).',
                       missing=missing, unknown=unknown)
    if unknown:
        return _result('warn', 'Accessibility not confirmed: ' + ', '.join(unknown),
                       'Confirm these features with the venue.', missing=[], unknown=unknown)
    return _result('pass', 'Required accessibility features confirmed.', missing=[], unknown=[])


async def check_congestion(stop: dict[str, Any], deps: Deps) -> dict[str, Any]:
    area = stop.get('area_name')
    if not area:
        return _result('skipped', 'No area_name; congestion was not checked.')
    try:
        reading = await deps.get_congestion(str(area))
    except Exception as exc:
        return _result('warn', f'Congestion lookup failed: {exc}',
                       'Check crowd levels for this area before going.')
    level = reading.get('congestion_level')
    rank = reading.get('congestion_rank')
    if rank is None:
        return _result('warn', f'Unrecognized congestion level: {level}',
                       'Check crowd levels for this area before going.', level=level, rank=rank)
    if rank >= CONGESTION_WARN_RANK:
        return _result('warn', f'Area is currently {level}.',
                       'Consider an alternative spot or a later visit. This is the current reading only; the forecast is not yet read.',
                       level=level, rank=rank)
    return _result('pass', f'Area is currently {level}.', level=level, rank=rank)


async def check_traffic(stop: dict[str, Any], deps: Deps) -> dict[str, Any]:
    road = stop.get('road')
    if not road:
        return _result('skipped', 'No road; traffic was not checked.')
    try:
        report = await deps.get_traffic(str(road))
    except Exception as exc:
        return _result('warn', f'Traffic lookup failed: {exc}', 'Check live traffic for this route before leaving.')
    if report.get('protest_flag'):
        return _result('fail', f'Protest-related incident reported near {road}.',
                       'Reroute the transit leg or move this stop later (rebalance_itinerary with a traffic_incident trigger).',
                       incident_count=report.get('incident_count', 0))
    if report.get('incident_count', 0) > 0:
        return _result('warn', f"{report['incident_count']} traffic incident(s) reported near {road}.",
                       'Allow extra travel time or check the route before leaving.',
                       incident_count=report['incident_count'])
    return _result('pass', f'No incidents reported near {road}.', incident_count=0)


def find_gaps(stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for index in range(1, len(stops)):
        previous, current = stops[index - 1], stops[index]
        if not previous.get('arrive') or not current.get('arrive'):
            continue
        previous_end = to_minutes(previous['arrive']) + stay_minutes(previous)
        travel = int(current.get('travel_minutes_from_prev') or 0)
        free_start = previous_end + travel
        gap = to_minutes(current['arrive']) - free_start
        gaps.append({
            'after_index': index - 1,
            'before_index': index,
            'start': format_minutes(free_start),
            'gap_minutes': gap,
            'is_overlap': gap < 0,
            'is_idle': gap > IDLE_GAP_THRESHOLD_MINUTES,
        })
    return gaps


async def qa_itinerary(
    itinerary: dict[str, Any],
    profile: dict[str, Any] | None = None,
    deps: Deps | None = None,
) -> dict[str, Any]:
    deps = deps or Deps()
    profile = profile or {}
    day = itinerary.get('date')
    stops = itinerary.get('stops') or []
    required = required_features(profile)
    unknown_needs = [str(need) for need in profile.get('needs') or [] if str(need).lower() not in ACCESSIBILITY_REQUIREMENTS]

    failures: list[str] = []
    warnings: list[str] = []
    remediation: list[str] = []
    stop_reports: list[dict[str, Any]] = []

    if not stops:
        failures.append('Itinerary has no stops.')
        remediation.append('Add at least one stop.')

    for index, stop in enumerate(stops):
        name = str(stop.get('name') or f'stop {index + 1}')
        checks_out = {
            'temporal': check_temporal(stop, day),
            'accessibility': await check_accessibility(stop, required, deps),
            'congestion': await check_congestion(stop, deps),
            'traffic': await check_traffic(stop, deps),
        }
        for check_name, result in checks_out.items():
            label = f'Stop {index + 1} ({name}) [{check_name}]'
            if result['status'] == 'fail':
                failures.append(f"{label}: {result['detail']}")
            elif result['status'] == 'warn':
                warnings.append(f"{label}: {result['detail']}")
            if result.get('remediation') and result['status'] in ('fail', 'warn'):
                remediation.append(f"Stop {index + 1} ({name}): {result['remediation']}")
        stop_reports.append({
            'index': index,
            'name': name,
            'status': _overall([result['status'] for result in checks_out.values()]),
            'checks': checks_out,
        })

    gaps = find_gaps(stops)
    idle_slots: list[dict[str, Any]] = []
    for gap in gaps:
        if gap['is_overlap']:
            failures.append(f"Stops {gap['after_index'] + 1} and {gap['before_index'] + 1} overlap by {-gap['gap_minutes']} minutes.")
            remediation.append('Shift the later stop, or shorten the earlier stay or the travel time.')
        elif gap['is_idle']:
            idle_slots.append({**gap, 'suggestion': 'Use get_idle_events to find free cultural events for this window.'})
            remediation.append(
                f"{gap['gap_minutes']}-minute idle gap after stop {gap['after_index'] + 1}: consider a nearby free cultural event."
            )

    status = 'fail' if failures else 'warn' if warnings else 'pass'
    return {
        'status': status,
        'date': day,
        'required_features': required,
        'unknown_needs': unknown_needs,
        'stops': stop_reports,
        'gaps': gaps,
        'idle_slots': idle_slots,
        'failures': failures,
        'warnings': warnings,
        'remediation': remediation,
        'sources': ['TourAPI restdate and usetime', 'KTO barrier-free API', 'Seoul Real-Time City Data', 'TOPIS incidents'],
    }

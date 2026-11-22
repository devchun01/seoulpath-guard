'''Dynamic rebalancing engine.

Triggers are applied in a fixed order: closed venues, congestion, traffic incidents,
barrier-free violations, then idle gaps. Idle gaps are measured last, on the final schedule.
Substitutes come from a candidate pool supplied by the caller, because the Kakao PlayMCP
place search is not yet implemented. Every change is recorded with an explanation, and the
result is QA-checked again.
'''

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from seoulpath_guard.qa import checks
from seoulpath_guard.tools import cultural_events, tourapi

DEFAULT_MAX_DISTANCE_KM = 3.0
TRIGGER_ORDER = {
    'closed_venue': 0,
    'congestion': 1,
    'traffic_incident': 2,
    'barrier_free_violation': 3,
    'idle_gap': 4,
}


@dataclass
class EngineDeps(checks.Deps):
    get_idle_events: Callable[..., Awaitable[dict[str, Any]]] = cultural_events.get_idle_events


def _name(stop: dict[str, Any]) -> str:
    return str(stop.get('name') or stop.get('content_id') or 'unnamed stop')


def _has_coords(stop: dict[str, Any]) -> bool:
    return stop.get('lat') is not None and stop.get('lon') is not None


def _distance_km(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if not (_has_coords(a) and _has_coords(b)):
        return None
    return cultural_events.haversine_km(float(a['lat']), float(a['lon']), float(b['lat']), float(b['lon']))


def _recompute_times(stops: list[dict[str, Any]], start: int) -> None:
    current = start
    for index, stop in enumerate(stops):
        if index > 0:
            previous = stops[index - 1]
            travel = int(stop.get('travel_minutes_from_prev') or 0)
            current += checks.stay_minutes(previous) + travel
        stop['arrive'] = checks.format_minutes(current)


def _locate(stops: list[dict[str, Any]], target: dict[str, Any]) -> int | None:
    for index, stop in enumerate(stops):
        if stop is target:
            return index
    return None


def _find_target(stops: list[dict[str, Any]], trigger: dict[str, Any]) -> dict[str, Any] | None:
    if trigger.get('stop_index') is not None:
        index = int(trigger['stop_index'])
        return stops[index] if 0 <= index < len(stops) else None
    if trigger.get('content_id'):
        return next((s for s in stops if s.get('content_id') == trigger['content_id']), None)
    if trigger.get('name'):
        return next((s for s in stops if s.get('name') == trigger['name']), None)
    return None


def _as_stop(candidate: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    stop = copy.deepcopy(candidate)
    stop['arrive'] = original.get('arrive')
    stop['stay_minutes'] = checks.stay_minutes(original)
    stop['travel_minutes_from_prev'] = original.get('travel_minutes_from_prev', 0)
    return stop


async def _candidate_ok(
    candidate: dict[str, Any],
    state: dict[str, Any],
    original: dict[str, Any],
    required: list[str],
) -> tuple[bool, str]:
    day = state['day']
    arrive = original.get('arrive')
    if not day:
        return False, 'no itinerary date'
    if not arrive:
        return False, 'original stop has no arrival time'
    evaluation = tourapi.evaluate_visit(candidate.get('restdate'), candidate.get('usetime'), day, arrive)
    if evaluation['status'] != 'open':
        return False, f"hours check: {evaluation['status']}"
    deps: EngineDeps = state['deps']
    if required:
        cid = candidate.get('content_id')
        if not cid:
            return False, 'no content_id for accessibility check'
        try:
            record = await deps.get_barrier_free(str(cid))
        except Exception as exc:
            return False, f'accessibility lookup failed ({exc})'
        if not record.get('found'):
            return False, 'no barrier-free record'
        missing = [feature for feature in required if record.get('features', {}).get(feature) is not True]
        if missing:
            return False, 'not accessible: ' + ', '.join(missing)
    area = candidate.get('area_name')
    if area:
        try:
            reading = await deps.get_congestion(str(area))
        except Exception as exc:
            return False, f'congestion lookup failed ({exc})'
        rank = reading.get('congestion_rank')
        if rank is None or rank >= checks.CONGESTION_WARN_RANK:
            return False, f"congested ({reading.get('congestion_level')})"
    return True, 'ok'


async def _find_substitute(
    state: dict[str, Any],
    original: dict[str, Any],
    required: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    used = {s.get('content_id') for s in state['stops']}
    pool: list[tuple[float, dict[str, Any]]] = []
    for candidate in state['candidates']:
        cid = candidate.get('content_id')
        if not cid or cid in used:
            continue
        distance = _distance_km(original, candidate)
        if distance is not None and distance > state['max_km']:
            continue
        pool.append((distance if distance is not None else float('inf'), candidate))
    pool.sort(key=lambda item: item[0])
    rejected: list[str] = []
    for _, candidate in pool:
        ok, reason = await _candidate_ok(candidate, state, original, required)
        if ok:
            return candidate, rejected
        rejected.append(f'{_name(candidate)}: {reason}')
    return None, rejected


def _no_substitute_message(name: str, state: dict[str, Any], rejected: list[str]) -> str:
    detail = ('Rejected: ' + '; '.join(rejected)) if rejected else 'No candidates were supplied or none were nearby.'
    return f"No suitable substitute for {name} within {state['max_km']} km. {detail}"


def _replace(state: dict[str, Any], original: dict[str, Any], candidate: dict[str, Any], explanation: str) -> None:
    index = _locate(state['stops'], original)
    if index is None:
        state['unresolved'].append(f'{_name(original)}: no longer in the itinerary.')
        return
    state['stops'][index] = _as_stop(candidate, original)
    state['changes'].append({
        'type': 'substitute',
        'stop_index': index,
        'from': _name(original),
        'to': _name(candidate),
        'explanation': explanation,
    })


def _move_to_end(state: dict[str, Any], target: dict[str, Any], reason: str) -> None:
    stops = state['stops']
    name = _name(target)
    index = _locate(stops, target)
    if index is None:
        state['unresolved'].append(f'{name}: no longer in the itinerary.')
        return
    if state['start'] is None:
        state['unresolved'].append(f'{name}: cannot reorder because the first stop has no arrival time.')
        return
    if index == len(stops) - 1:
        state['unresolved'].append(f'{name}: {reason}, but it is already the last stop and no other position is available.')
        return
    moved = stops.pop(index)
    moved['travel_minutes_from_prev'] = 0
    moved['travel_needs_reestimate'] = True
    stops.append(moved)
    _recompute_times(stops, state['start'])
    state['changes'].append({
        'type': 'reorder',
        'stop': name,
        'from_index': index,
        'to_index': len(stops) - 1,
        'explanation': (f'{name} was moved to the end of the day because {reason}. '
                        'Later arrival times were recomputed. Its transit time must be re-estimated, '
                        'since route lookup is not yet implemented.'),
    })


async def _handle_closed(state: dict[str, Any], trigger: dict[str, Any], target: dict[str, Any] | None) -> None:
    if target is None:
        state['unresolved'].append('closed_venue trigger does not match any stop in the itinerary.')
        return
    name = _name(target)
    reason = trigger.get('reason') or 'closed'
    substitute, rejected = await _find_substitute(state, target, state['required'])
    if substitute is None:
        state['unresolved'].append(_no_substitute_message(name, state, rejected))
        return
    _replace(state, target, substitute,
             f'{name} is closed ({reason}); replaced with {_name(substitute)} at the same arrival time.')


async def _handle_congestion(state: dict[str, Any], trigger: dict[str, Any], target: dict[str, Any] | None) -> None:
    if target is None:
        state['unresolved'].append('congestion trigger does not match any stop in the itinerary.')
        return
    name = _name(target)
    level = trigger.get('level') or 'severely congested'
    substitute, _ = await _find_substitute(state, target, state['required'])
    if substitute is not None:
        _replace(state, target, substitute,
                 f'{name} is {level}; replaced with {_name(substitute)}, which the congestion check reports as less crowded.')
        return
    _move_to_end(state, target, f'it is {level} and no less crowded substitute was found')


async def _handle_traffic(state: dict[str, Any], trigger: dict[str, Any], target: dict[str, Any] | None) -> None:
    road = str(trigger.get('road') or '')
    if target is not None:
        targets = [target]
    elif road:
        targets = [s for s in state['stops'] if s.get('road') and (road in str(s['road']) or str(s['road']) in road)]
    else:
        targets = []
    if not targets:
        road_label = road or 'not given'
        state['unresolved'].append(f'traffic_incident trigger matched no stops (road: {road_label}).')
        return
    for stop in targets:
        road_name = road or str(stop.get('road'))
        _move_to_end(state, stop, f'of a traffic incident or protest on {road_name}')


async def _handle_barrier(state: dict[str, Any], trigger: dict[str, Any], target: dict[str, Any] | None) -> None:
    if target is None:
        state['unresolved'].append('barrier_free_violation trigger does not match any stop in the itinerary.')
        return
    required = checks.required_features({'needs': trigger['needs']}) if trigger.get('needs') else state['required']
    if not required:
        state['unresolved'].append('No accessibility needs in the profile or the trigger; nothing to check.')
        return
    name = _name(target)
    cid = target.get('content_id')
    if not cid:
        state['unresolved'].append(f'{name}: no content_id, so accessibility cannot be verified.')
        return
    deps: EngineDeps = state['deps']
    try:
        record = await deps.get_barrier_free(str(cid))
    except Exception as exc:
        state['unresolved'].append(f'{name}: accessibility lookup failed ({exc}).')
        return
    missing = [feature for feature in required if record.get('features', {}).get(feature) is not True]
    if record.get('found') and not missing:
        state['changes'].append({'type': 'no_change', 'stop': name,
                                 'explanation': f'{name} meets the accessibility needs; no swap was made.'})
        return
    reason = ', '.join(missing) if missing else 'no barrier-free record'
    substitute, rejected = await _find_substitute(state, target, required)
    if substitute is None:
        state['unresolved'].append(_no_substitute_message(name, state, rejected))
        return
    _replace(state, target, substitute,
             f'{name} does not meet the accessibility needs ({reason}); replaced with {_name(substitute)}.')


async def _handle_idle(state: dict[str, Any], trigger: dict[str, Any], target: dict[str, Any] | None) -> None:
    stops = state['stops']
    idle_gaps = [gap for gap in checks.find_gaps(stops) if gap['is_idle']]
    if not idle_gaps:
        state['changes'].append({'type': 'no_change', 'explanation': 'No idle gap above the threshold; no events were injected.'})
        return
    on_day = date.fromisoformat(state['day']) if state['day'] else None
    deps: EngineDeps = state['deps']
    for gap in idle_gaps:
        previous = stops[gap['after_index']]
        label = f"{gap['gap_minutes']}-minute gap after {_name(previous)} starting {gap['start']}"
        if not _has_coords(previous):
            state['unresolved'].append(f'{label}: no coordinates to search from.')
            continue
        try:
            result = await deps.get_idle_events(float(previous['lat']), float(previous['lon']),
                                                gap['gap_minutes'], on_day=on_day)
        except Exception as exc:
            state['unresolved'].append(f'{label}: event lookup failed ({exc}).')
            continue
        events = result.get('events', [])
        state['injected'].append({
            'after_stop_index': gap['after_index'],
            'start': gap['start'],
            'free_minutes': gap['gap_minutes'],
            'events': events,
        })
        if events:
            state['changes'].append({'type': 'inject', 'explanation': f'{label}: {len(events)} free cultural event(s) found within walking range.'})
        else:
            state['changes'].append({'type': 'no_change', 'explanation': f'{label}: no free cultural events found within walking range.'})


HANDLERS = {
    'closed_venue': _handle_closed,
    'congestion': _handle_congestion,
    'traffic_incident': _handle_traffic,
    'barrier_free_violation': _handle_barrier,
    'idle_gap': _handle_idle,
}


async def rebalance_itinerary(
    itinerary: dict[str, Any],
    triggers: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    deps: EngineDeps | None = None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
) -> dict[str, Any]:
    deps = deps or EngineDeps()
    profile = profile or {}
    stops = copy.deepcopy(itinerary.get('stops') or [])
    start = checks.to_minutes(stops[0]['arrive']) if stops and stops[0].get('arrive') else None
    state: dict[str, Any] = {
        'stops': stops,
        'changes': [],
        'unresolved': [],
        'injected': [],
        'day': itinerary.get('date'),
        'required': checks.required_features(profile),
        'candidates': copy.deepcopy(candidates or []),
        'deps': deps,
        'max_km': max_distance_km,
        'start': start,
    }

    resolved: list[tuple[int, str, dict[str, Any], dict[str, Any] | None]] = []
    for trigger in triggers or []:
        trigger_type = trigger.get('type')
        if trigger_type not in HANDLERS:
            state['unresolved'].append(f'Unknown trigger type: {trigger_type}')
            continue
        resolved.append((TRIGGER_ORDER[trigger_type], trigger_type, trigger, _find_target(stops, trigger)))
    resolved.sort(key=lambda item: item[0])

    for _, trigger_type, trigger, target in resolved:
        await HANDLERS[trigger_type](state, trigger, target)

    new_itinerary = {**itinerary, 'stops': stops}
    post = await checks.qa_itinerary(new_itinerary, profile, deps=deps)
    return {
        'itinerary': new_itinerary,
        'changes': state['changes'],
        'diff_explanation': [change['explanation'] for change in state['changes'] if change.get('explanation')],
        'injected_events': state['injected'],
        'unresolved': state['unresolved'],
        'post_qa': {
            'status': post['status'],
            'failures': post['failures'],
            'warnings': post['warnings'],
            'remediation': post['remediation'],
        },
    }

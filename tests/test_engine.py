'''Offline smoke tests for the QA and rebalance engines.

Run with: python tests/test_engine.py   (or pytest tests/test_engine.py)
All external lookups are replaced with fakes, so no API keys or network are needed.
'''

import asyncio
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))

from seoulpath_guard.qa import checks  # noqa: E402
from seoulpath_guard.rebalance import engine  # noqa: E402

DAY = '2026-11-24'  # Tuesday
MONDAY = '2026-11-23'

ACCESS = {
    'open_accessible': {'found': True, 'features': {
        'wheelchair_access': True, 'elevator': True, 'accessible_restroom': True, 'stroller_friendly': True}},
    'stairs_only': {'found': True, 'features': {
        'wheelchair_access': False, 'elevator': False, 'accessible_restroom': None, 'stroller_friendly': False}},
    'museum': {'found': True, 'features': {
        'wheelchair_access': True, 'elevator': True, 'accessible_restroom': True, 'stroller_friendly': True}},
}


async def fake_barrier(cid):
    return ACCESS.get(cid, {'found': False, 'features': {}})


async def fake_congestion(area):
    if area == '명동':
        return {'congestion_level': '붐빔', 'congestion_rank': 4}
    return {'congestion_level': '여유', 'congestion_rank': 1}


async def fake_traffic(road):
    if road == '세종대로':
        return {'incident_count': 1, 'protest_related_count': 1, 'protest_flag': True, 'incidents': []}
    return {'incident_count': 0, 'protest_related_count': 0, 'protest_flag': False, 'incidents': []}


async def fake_idle(lat, lon, free_minutes, radius_km=2.0, on_day=None):
    return {'events': [{'title': 'Free pop-up', 'distance_km': 0.4}]}


DEPS = engine.EngineDeps(
    get_barrier_free=fake_barrier,
    get_congestion=fake_congestion,
    get_traffic=fake_traffic,
    get_idle_events=fake_idle,
)


def stop(name, cid, arrive, **kw):
    base = {
        'name': name,
        'content_id': cid,
        'arrive': arrive,
        'stay_minutes': 60,
        'travel_minutes_from_prev': 0,
        'restdate': '매주 월요일 휴무',
        'usetime': '09:00~18:00 (입장마감 17:00)',
        'lat': 37.5636,
        'lon': 126.9869,
    }
    base.update(kw)
    return base


def test_gap_detection_flags_idle_slot():
    stops = [stop('A', 'open_accessible', '10:00'),
             stop('B', 'open_accessible', '13:00', travel_minutes_from_prev=20)]
    gaps = checks.find_gaps(stops)
    assert gaps[0]['gap_minutes'] == 100, gaps
    assert gaps[0]['is_idle'] is True
    assert gaps[0]['is_overlap'] is False


def test_overlap_is_detected():
    stops = [stop('A', 'open_accessible', '10:00', stay_minutes=120),
             stop('B', 'open_accessible', '11:00')]
    gaps = checks.find_gaps(stops)
    assert gaps[0]['is_overlap'] is True


def test_closed_day_fails():
    result = checks.check_temporal(stop('A', 'x', '10:00'), MONDAY)
    assert result['status'] == 'fail', result


def test_outside_hours_fails():
    result = checks.check_temporal(stop('A', 'x', '19:00'), DAY)
    assert result['status'] == 'fail', result


def test_open_visit_passes():
    result = checks.check_temporal(stop('A', 'x', '10:00'), DAY)
    assert result['status'] == 'pass', result


def test_qa_accessibility_failure():
    itinerary = {'date': DAY, 'stops': [stop('Stairs venue', 'stairs_only', '10:00')]}
    report = asyncio.run(checks.qa_itinerary(itinerary, {'needs': ['wheelchair']}, deps=DEPS))
    assert report['status'] == 'fail', report
    assert any('[accessibility]' in f for f in report['failures']), report['failures']


def test_qa_congestion_warning_and_protest_failure():
    itinerary = {'date': DAY, 'stops': [
        stop('Myeongdong', 'open_accessible', '10:00', area_name='명동'),
        stop('Sejong', 'open_accessible', '12:00', road='세종대로'),
    ]}
    report = asyncio.run(checks.qa_itinerary(itinerary, {}, deps=DEPS))
    assert any('[congestion]' in w for w in report['warnings']), report['warnings']
    assert any('[traffic]' in f for f in report['failures']), report['failures']


def test_qa_reports_idle_slot():
    itinerary = {'date': DAY, 'stops': [
        stop('A', 'open_accessible', '10:00'),
        stop('B', 'open_accessible', '13:00', travel_minutes_from_prev=20),
    ]}
    report = asyncio.run(checks.qa_itinerary(itinerary, {}, deps=DEPS))
    assert len(report['idle_slots']) == 1, report['idle_slots']


def test_closed_venue_substitution_keeps_time():
    itinerary = {'date': DAY, 'stops': [
        stop('Closed palace', 'open_accessible', '10:00', lat=37.5796, lon=126.9770),
        stop('Lunch', 'open_accessible', '12:00'),
    ]}
    candidates = [stop('Nearby museum', 'museum', '10:00', lat=37.5800, lon=126.9780)]
    triggers = [{'type': 'closed_venue', 'stop_index': 0, 'reason': 'closed for maintenance'}]
    result = asyncio.run(engine.rebalance_itinerary(itinerary, triggers, {}, candidates, deps=DEPS))
    first = result['itinerary']['stops'][0]
    assert first['content_id'] == 'museum', first
    assert first['arrive'] == '10:00'
    assert result['changes'][0]['type'] == 'substitute'


def test_traffic_incident_reorders_and_recomputes_times():
    itinerary = {'date': DAY, 'stops': [
        stop('Sejong', 'open_accessible', '10:00', road='세종대로'),
        stop('Bukchon', 'open_accessible', '11:30', travel_minutes_from_prev=10),
    ]}
    triggers = [{'type': 'traffic_incident', 'road': '세종대로'}]
    result = asyncio.run(engine.rebalance_itinerary(itinerary, triggers, {}, [], deps=DEPS))
    stops = result['itinerary']['stops']
    assert stops[-1]['name'] == 'Sejong', [s['name'] for s in stops]
    assert stops[0]['name'] == 'Bukchon' and stops[0]['arrive'] == '10:00'
    assert stops[1]['arrive'] == '11:00', stops[1]


def test_idle_gap_injects_events_without_moving_stops():
    itinerary = {'date': DAY, 'stops': [
        stop('A', 'open_accessible', '10:00'),
        stop('B', 'open_accessible', '13:00', travel_minutes_from_prev=20),
    ]}
    result = asyncio.run(engine.rebalance_itinerary(itinerary, [{'type': 'idle_gap'}], {}, [], deps=DEPS))
    assert len(result['injected_events']) == 1, result['injected_events']
    assert result['injected_events'][0]['free_minutes'] == 100
    assert result['itinerary']['stops'][1]['arrive'] == '13:00'


def test_barrier_violation_swaps_for_accessible_venue():
    itinerary = {'date': DAY, 'stops': [
        stop('Old palace', 'stairs_only', '10:00', lat=37.5796, lon=126.9770),
    ]}
    candidates = [stop('Accessible hall', 'open_accessible', '10:00', lat=37.5800, lon=126.9780)]
    triggers = [{'type': 'barrier_free_violation', 'stop_index': 0, 'needs': ['wheelchair']}]
    result = asyncio.run(engine.rebalance_itinerary(itinerary, triggers, {}, candidates, deps=DEPS))
    assert result['itinerary']['stops'][0]['name'] == 'Accessible hall', result['changes']


def test_input_itinerary_is_not_mutated():
    itinerary = {'date': DAY, 'stops': [stop('Sejong', 'open_accessible', '10:00', road='세종대로')]}
    before = copy.deepcopy(itinerary)
    asyncio.run(engine.rebalance_itinerary(itinerary, [{'type': 'traffic_incident', 'road': '세종대로'}],
                                           {}, [], deps=DEPS))
    assert itinerary == before


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_') and callable(value)]
    for test in tests:
        test()
        print('PASS', test.__name__)
    print(f'{len(tests)} tests passed')

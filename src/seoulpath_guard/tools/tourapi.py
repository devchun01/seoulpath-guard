'''TourAPI / Seoul Public Data client and free-text parsers for restdate and usetime.

Parsers turn Korean free-text hours and rest-day fields into structured rules.
Anything they cannot interpret is reported as unknown rather than guessed.
'''

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

WEEKDAY_CHARS = '월화수목금토일'
WEEKDAYS = {char: index for index, char in enumerate(WEEKDAY_CHARS)}  # Monday = 0
MONTHLY_RE = re.compile(r'(첫째|둘째|셋째|넷째|마지막)\s*([월화수목금토일])\s*요일')
WEEKLY_RE = re.compile(r'([월화수목금토일])\s*요일')
FIXED_DATE_RE = re.compile(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일')
HOLIDAY_RE = re.compile(r'(설날|추석|명절|신정|크리스마스)')
YEAR_ROUND_RE = re.compile(r'연중\s*무휴|년중\s*무휴|무휴')
TIME_RE = re.compile(r'(오전|오후)?\s*(\d{1,2})\s*(?::|시)\s*(\d{2})?')
ENTRY_RE = re.compile(r'마지막\s*입장|입장\s*마감|라스트\s*오더|마지막\s*주문')
ORDINAL_NTH = {'첫째': 1, '둘째': 2, '셋째': 3, '넷째': 4}


def parse_restdate(text: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        'raw': text or '',
        'weekly_closed': [],
        'monthly_closed': [],
        'fixed_dates': [],
        'holiday_closures': [],
        'year_round_open': False,
    }
    if not text or not text.strip():
        return result

    result['monthly_closed'] = [
        {'ordinal': ordinal, 'weekday': WEEKDAYS[weekday]}
        for ordinal, weekday in MONTHLY_RE.findall(text)
    ]
    remainder = MONTHLY_RE.sub(' ', text)
    result['weekly_closed'] = sorted({WEEKDAYS[weekday] for weekday in WEEKLY_RE.findall(remainder)})
    result['fixed_dates'] = sorted({f'{int(month):02d}-{int(day):02d}' for month, day in FIXED_DATE_RE.findall(text)})
    result['holiday_closures'] = sorted(set(HOLIDAY_RE.findall(text)))

    has_rule = any(result[key] for key in ('weekly_closed', 'monthly_closed', 'fixed_dates', 'holiday_closures'))
    result['year_round_open'] = bool(YEAR_ROUND_RE.search(text)) and not has_rule
    return result


def _is_last_weekday_of_month(day: date) -> bool:
    return (day + timedelta(days=7)).month != day.month


def _nth_weekday_matches(day: date, ordinal: str) -> bool:
    if ordinal == '마지막':
        return _is_last_weekday_of_month(day)
    return (day.day - 1) // 7 + 1 == ORDINAL_NTH[ordinal]


def is_closed_on(parsed: dict[str, Any], day: date) -> bool | None:
    if parsed['year_round_open']:
        return False
    has_info = any(parsed[key] for key in ('weekly_closed', 'monthly_closed', 'fixed_dates'))
    if not has_info:
        return None
    if day.weekday() in parsed['weekly_closed']:
        return True
    for rule in parsed['monthly_closed']:
        if rule['weekday'] == day.weekday() and _nth_weekday_matches(day, rule['ordinal']):
            return True
    return f'{day.month:02d}-{day.day:02d}' in parsed['fixed_dates']


def _to_minutes(match: re.Match[str]) -> int | None:
    ampm, hour_text, minute_text = match.group(1), match.group(2), match.group(3)
    hour = int(hour_text)
    minute = int(minute_text) if minute_text else 0
    if ampm == '오후' and hour < 12:
        hour += 12
    if ampm == '오전' and hour == 12:
        hour = 0
    if hour > 24 or minute > 59:
        return None
    return hour * 60 + minute


def _format_minutes(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def parse_usetime(text: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        'raw': text or '',
        'is_24h': False,
        'open': None,
        'close': None,
        'overnight': False,
        'last_entry': None,
    }
    if not text or not text.strip():
        return result

    if '24시간' in text:
        result['is_24h'] = True
        result['open'], result['close'] = '00:00', '24:00'
        return result

    entry = ENTRY_RE.search(text)
    main_text = text[:entry.start()] if entry else text
    if entry:
        entry_match = TIME_RE.search(text[entry.end():])
        if entry_match:
            result['last_entry'] = _format_minutes(_to_minutes(entry_match))

    minutes = [value for value in (_to_minutes(m) for m in TIME_RE.finditer(main_text)) if value is not None]
    if len(minutes) >= 2:
        open_minutes, close_minutes = minutes[0], minutes[1]
        result['open'] = _format_minutes(open_minutes)
        result['close'] = _format_minutes(close_minutes)
        result['overnight'] = close_minutes <= open_minutes
    elif len(minutes) == 1:
        result['open'] = _format_minutes(minutes[0])
    return result


def evaluate_visit(
    restdate: str | None,
    usetime: str | None,
    visit_date: str | None = None,
    visit_time: str | None = None,
) -> dict[str, Any]:
    parsed_rest = parse_restdate(restdate)
    parsed_use = parse_usetime(usetime)
    result: dict[str, Any] = {
        'restdate': parsed_rest,
        'usetime': parsed_use,
        'status': 'unknown',
        'reason': 'No visit date given; returned parsed rules only.',
    }
    if not visit_date:
        return result

    day = date.fromisoformat(visit_date)
    closed = is_closed_on(parsed_rest, day)
    if closed is True:
        result.update(status='closed_day', reason=f'Rest day on {day.isoformat()} per restdate.')
        return result
    if not visit_time:
        result.update(status='open_day' if closed is False else 'unknown',
                      reason='No visit time given; only the rest-day rule was checked.')
        return result

    hour_text, minute_text = visit_time.split(':')[:2]
    minutes = int(hour_text) * 60 + int(minute_text)
    open_text, close_text = parsed_use['open'], parsed_use['close']
    if open_text is None or close_text is None:
        result.update(status='unknown', reason='Opening hours could not be parsed from usetime.')
        return result

    open_minutes = int(open_text[:2]) * 60 + int(open_text[3:])
    close_minutes = int(close_text[:2]) * 60 + int(close_text[3:])
    if parsed_use['overnight']:
        within = minutes >= open_minutes or minutes < close_minutes
    else:
        within = open_minutes <= minutes < close_minutes
    if not within:
        result.update(status='outside_hours', reason=f'Visit at {visit_time} is outside {open_text}-{close_text}.')
        return result

    last_entry = parsed_use['last_entry']
    if last_entry:
        last_minutes = int(last_entry[:2]) * 60 + int(last_entry[3:])
        if minutes > last_minutes:
            result.update(status='after_last_entry', reason=f'Visit at {visit_time} is after last entry {last_entry}.')
            return result

    result.update(status='open', reason=f'Open at {visit_time} on {day.isoformat()}.')
    return result


async def get_attraction_info(content_id: str) -> dict:
    raise NotImplementedError


async def search_events(date_from: str, date_to: str, area: str | None = None) -> dict:
    raise NotImplementedError

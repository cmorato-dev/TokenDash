"""Shared quota value objects: no provider endpoints.

The Codex reader and the official Claude client build the same readings here.
Labels and failure messages are stored in English and translated when they are
shown (display_quota, and gettext on ProviderStatus.last_error), so each visitor
reads them in their own language.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.utils import formats, timezone
from django.utils.translation import gettext as _, gettext_noop, pgettext

# Claude publishes these two windows for Pro/Max subscriptions.
CLAUDE_WINDOWS = {'five_hour': ('session', gettext_noop('5-hour session')), 'seven_day': ('weekly_all', gettext_noop('Week · all models'))}
CODEX_HOURS = re.compile(r'Codex · (\d+) h window')


class ScrapeFailure(Exception):
    state = 'error'
    message = gettext_noop('Could not refresh. Check the connection and the settings.')

    def __init__(self, message=None):
        # A subclass may pass a more specific reason. Without this, the instance
        # message would be lost and every failure would show the generic text.
        super().__init__(message or self.message)
        if message:
            self.message = message


class SessionExpired(ScrapeFailure):
    state = 'expired'
    message = gettext_noop('Session expired or missing, sign in again.')


class VerificationRequired(ScrapeFailure):
    state = 'blocked'
    message = gettext_noop('The provider asks for a manual verification in the browser.')


class QuotaUnavailable(ScrapeFailure):
    state = 'unavailable'
    message = gettext_noop('No recognisable quota percentage was found. Check the connection in "Connect accounts"; your plan may not publish this metric.')


@dataclass(frozen=True)
class QuotaReading:
    key: str
    label: str
    used_percent: Decimal
    reset_text: str = ''
    resets_at: str = ''  # ISO 8601 when the provider publishes the reset instant

    def as_json(self):
        data = {'key': self.key, 'label': self.label, 'used_percent': str(self.used_percent), 'reset_text': self.reset_text}
        if self.resets_at:
            data['resets_at'] = self.resets_at
        return data


def quota_reading(key, label, used, resets_epoch=None):
    """A provider-published percentage, or None if it is not a valid 0-100 number."""
    if isinstance(used, bool):
        return None
    try:
        percent = Decimal(str(used))
    except (InvalidOperation, ValueError):
        return None
    if not percent.is_finite() or not 0 <= percent <= 100:
        return None
    resets_at, reset_text = '', ''
    if isinstance(resets_epoch, (int, float)) and not isinstance(resets_epoch, bool) and resets_epoch > 0:
        moment = datetime.fromtimestamp(resets_epoch, dt_timezone.utc)
        resets_at = moment.isoformat()
        reset_text = reset_sentence(moment)
    return QuotaReading(key, label, percent.quantize(Decimal('0.01')), reset_text, resets_at)


def reset_sentence(moment):
    """«Resets on Oct 27 at 07:41», in the active language and the local time zone."""
    local = timezone.localtime(moment)
    return _('Resets on %(day)s at %(time)s') % {
        'day': formats.date_format(local, pgettext('day and month of a reset', 'M j')),
        'time': formats.date_format(local, 'H:i')}


def display_quota(quota):
    """A stored quota with its label and reset sentence in the active language."""
    quota = dict(quota)
    label = quota.get('label') or ''
    hours = CODEX_HOURS.fullmatch(label)
    quota['label'] = _('Codex · %(hours)s h window') % {'hours': hours[1]} if hours else (_(label) if label else '')
    try:
        quota['reset_text'] = reset_sentence(datetime.fromisoformat(quota['resets_at']))
    except (KeyError, TypeError, ValueError):
        quota['reset_text'] = quota.get('reset_text') or ''
    return quota


def window_key(minutes):
    # Kept in English: display_quota translates them, «Codex · N h window» included.
    if minutes <= 6 * 60:
        return 'session', f'Codex · {round(minutes / 60)} h window'
    if 6 * 24 * 60 <= minutes <= 8 * 24 * 60:
        return 'weekly', gettext_noop('Codex · week')
    if minutes >= 28 * 24 * 60:
        return 'monthly', gettext_noop('Codex · month')
    return f'window_{int(minutes)}m', f'Codex · {round(minutes / 60)} h window'


def readings_from_windows(windows):
    """windows: [{'used_percent', 'window_minutes', 'resets_at' (epoch seconds)}]."""
    readings, seen = [], set()
    for window in windows or []:
        try:
            minutes = float(window['window_minutes'])
        except (KeyError, TypeError, ValueError):
            continue
        if minutes <= 0:
            continue
        key, label = window_key(minutes)
        reading = quota_reading(key, label, window.get('used_percent'), window.get('resets_at'))
        if reading is None or key in seen:
            continue
        seen.add(key)
        readings.append(reading)
    return readings


def claude_readings(windows):
    """windows: [{'name': 'five_hour'|'seven_day', 'used_percentage', 'resets_at' (epoch seconds)}]."""
    readings = []
    for window in windows or []:
        name = window.get('name')
        if name not in CLAUDE_WINDOWS:
            continue
        key, label = CLAUDE_WINDOWS[name]
        reading = quota_reading(key, label, window.get('used_percentage'), window.get('resets_at'))
        if reading:
            readings.append(reading)
    return readings

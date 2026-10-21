"""Shared quota value objects: no provider endpoints.

The Codex reader and the official Claude client build the same readings here.
"""
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.utils import formats, timezone

# Claude publishes these two windows for Pro/Max subscriptions.
CLAUDE_WINDOWS = {'five_hour': ('session', 'Sesión de 5 horas'), 'seven_day': ('weekly_all', 'Semana · todos los modelos')}


class ScrapeFailure(Exception):
    state = 'error'
    message = 'No se pudo actualizar. Revisar conexión y configuración.'

    def __init__(self, message=None):
        # A subclass may pass a more specific reason. Without this, the instance
        # message would be lost and every failure would show the generic text.
        super().__init__(message or self.message)
        if message:
            self.message = message


class SessionExpired(ScrapeFailure):
    state = 'expired'
    message = 'Sesión expirada o ausente, reautenticar.'


class VerificationRequired(ScrapeFailure):
    state = 'blocked'
    message = 'El proveedor requiere una verificación manual en el navegador.'


class QuotaUnavailable(ScrapeFailure):
    state = 'unavailable'
    message = 'No hemos encontrado un porcentaje de cuota reconocible. Comprueba la conexión en «Conectar cuentas»; es posible que tu plan no publique esta métrica.'


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
        reset_text = 'Se reinicia el ' + formats.date_format(timezone.localtime(moment), 'j/n \\a \\l\\a\\s H:i')
    return QuotaReading(key, label, percent.quantize(Decimal('0.01')), reset_text, resets_at)


def window_key(minutes):
    if minutes <= 6 * 60:
        return 'session', f'Codex · ventana de {round(minutes / 60)} h' if minutes != 300 else 'Codex · ventana de 5 h'
    if 6 * 24 * 60 <= minutes <= 8 * 24 * 60:
        return 'weekly', 'Codex · semana'
    if minutes >= 28 * 24 * 60:
        return 'monthly', 'Codex · mes'
    return f'window_{int(minutes)}m', f'Codex · ventana de {round(minutes / 60)} h'


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

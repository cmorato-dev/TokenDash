"""Screenshots of the dashboard with invented but plausible data, for the README.

Runs on its own test database, never on the deployment's data, and writes
docs/img/panel.png (both accounts) and docs/img/panel-una-cuenta.png (only Claude).
"""
import os
import random
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from django.db import connection
from django.test import RequestFactory
from django.test.utils import setup_test_environment
from django.utils import formats, timezone
from playwright.sync_api import sync_playwright

from dashboard.models import ProviderStatus, RefreshSettings, UsageLog
from dashboard.views import DashboardView, HistoryView, StatusView
from scraper.models import ProviderCredential

setup_test_environment()
connection.creation.create_test_db(verbosity=0)
factory = RequestFactory()
user = SimpleNamespace(is_authenticated=True, is_staff=True, username='admin')
now = timezone.now()
rng = random.Random(21)


def call_view(view, path):
    request = factory.get(path)
    request.user = user
    request.session = {}
    response = view.as_view()(request)
    if hasattr(response, 'render'):
        response.render()
    return response.content


def iso(delta):
    return (now + delta).isoformat()


def reset_text(delta):
    # The same sentence the readers write (scraper/quotas.py).
    moment = timezone.localtime(now + delta)
    return f"Se reinicia el {formats.date_format(moment, 'j/n')} a las {formats.date_format(moment, 'H:i')}"


def seed_history(status, session_key, weekly_key, weekly_reset, intensity):
    """A week of readings every 20 minutes: 5-hour windows during the day, a weekly total that grows."""
    readings, session, weekly, window_end = [], 0.0, 0.0, None
    moment = now - timedelta(days=6, hours=now.hour, minutes=now.minute)
    while moment <= now:
        local = timezone.localtime(moment)
        if window_end and moment >= window_end:
            session, window_end = 0.0, None
        if moment.weekday() == weekly_reset and local.hour == 7 and local.minute < 20:
            weekly = 0.0
        if 9 <= local.hour < 24 and rng.random() < 0.45:
            step = rng.uniform(1, 6) * intensity
            window_end = window_end or moment + timedelta(hours=5)
            session = min(100.0, session + step)
            weekly = min(100.0, weekly + step / 7)
        if window_end:
            readings.append(UsageLog(provider=status, quota_key=session_key, quota_label='5 horas',
                                     used_percent=round(session, 2), observed_at=moment))
        readings.append(UsageLog(provider=status, quota_key=weekly_key, quota_label='Semana',
                                 used_percent=round(weekly, 2), observed_at=moment))
        moment += timedelta(minutes=20)
    UsageLog.objects.bulk_create(readings)


chatgpt = ProviderStatus.objects.get(provider='chatgpt')
claude = ProviderStatus.objects.get(provider='claude')
seed_history(chatgpt, 'session', 'weekly', weekly_reset=0, intensity=1.2)
seed_history(claude, 'session', 'weekly_all', weekly_reset=5, intensity=1.7)
ProviderStatus.objects.filter(pk=chatgpt.pk).update(
    collection_mode='api', state='ok', used_percent=23, quota_label='Codex · ventana de 5 h',
    last_success_at=now - timedelta(minutes=4), last_attempt_at=now - timedelta(minutes=4), quotas=[
        {'key': 'session', 'label': 'Codex · ventana de 5 h', 'used_percent': '23.00', 'reset_text': reset_text(timedelta(hours=3, minutes=12)), 'resets_at': iso(timedelta(hours=3, minutes=12))},
        {'key': 'weekly', 'label': 'Codex · semana', 'used_percent': '41.00', 'reset_text': '', 'resets_at': iso(timedelta(days=4, hours=6))}])
ProviderCredential.objects.create(provider=chatgpt, secret='demo')
ProviderStatus.objects.filter(pk=claude.pk).update(
    collection_mode='client', state='ok', used_percent=67, quota_label='Sesión de 5 horas',
    last_success_at=now - timedelta(minutes=4), last_attempt_at=now - timedelta(minutes=4), quotas=[
        {'key': 'session', 'label': 'Sesión de 5 horas', 'used_percent': '67.00', 'reset_text': reset_text(timedelta(hours=1, minutes=48)), 'resets_at': iso(timedelta(hours=1, minutes=48))},
        {'key': 'weekly_all', 'label': 'Semana', 'used_percent': '84.00', 'reset_text': '', 'resets_at': iso(timedelta(days=2, hours=14))}])

output = ROOT / 'docs' / 'img'
output.mkdir(parents=True, exist_ok=True)


def views():
    # Rendered before Playwright starts: its event loop does not allow database queries.
    return {
        '/': call_view(DashboardView, '/'),
        '/api/status/': call_view(StatusView, '/api/status/'),
        '/api/history/': call_view(HistoryView, '/api/history/?days=7'),
    }


def capture(page, pages, name):
    def route_request(route):
        path = urlparse(route.request.url).path
        if path.startswith('/static/'):
            target = settings.STATIC_ROOT / path.removeprefix('/static/')
            route.fulfill(body=target.read_bytes(), content_type='text/css' if path.endswith('.css') else 'application/javascript')
        elif path in pages:
            route.fulfill(body=pages[path], content_type='text/html' if path == '/' else 'application/json')
        else:
            route.fulfill(status=404)
    page.unroute('**/*')
    page.route('**/*', route_request)
    page.goto('http://tokendash.test/', wait_until='networkidle')
    page.wait_for_timeout(500)
    assert not page.locator('#feedback').inner_text()
    page.screenshot(path=str(output / name), full_page=True)


with patch('scraper.claude_client_views.client_available', return_value=True):
    both = views()
    RefreshSettings.objects.filter(pk=RefreshSettings.load().pk).update(accounts='claude')
    single = views()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 900}, device_scale_factor=1)
    capture(page, both, 'panel.png')
    capture(page, single, 'panel-una-cuenta.png')
    browser.close()
print(f'Capturas en {output}')

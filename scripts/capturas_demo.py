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


# Weekly renewals at a fixed local time, a week after the drop in the history below.
midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
CHATGPT_WEEK = midnight + timedelta(days=4, hours=22, minutes=35)  # dropped 3 days ago at 22:35
CLAUDE_WEEK = midnight + timedelta(days=3, hours=7, minutes=35)    # dropped 4 days ago at 7:35


def reset_text(delta):
    # The same sentence the readers write (scraper/quotas.py).
    moment = timezone.localtime(now + delta)
    return f"Se reinicia el {formats.date_format(moment, 'j/n')} a las {formats.date_format(moment, 'H:i')}"


# The chart draws the daily average of each limit. Every series below is the
# average of one day, from six days ago to today, and today's value is the one
# the card shows, so the chart and the cards tell the same story. The weekly
# limits drop on the day they renewed (the cards give the next renewal).
CHATGPT = {'session': [34, 18, 46, 27, 52, 15, 23], 'weekly': [55, 63, 72, 79, 9, 24, 41]}
CLAUDE = {'session': [58, 41, 72, 49, 63, 38, 67], 'weekly_all': [80, 88, 12, 31, 50, 67, 84]}


def seed_history(status, series):
    """Readings every 20 minutes from 8:00 to midnight, around each day's average."""
    readings = []
    today = timezone.localtime(now).replace(hour=8, minute=0, second=0, microsecond=0)
    for key, days in series.items():
        for days_ago, average in zip(range(6, -1, -1), days):
            moment, end = today - timedelta(days=days_ago), today - timedelta(days=days_ago - 1, hours=8)
            values = []
            while moment < min(end, now):
                # Today stays on the card's value, so its average is exactly that number.
                noise = rng.uniform(-2, 2) if days_ago else 0
                values.append((moment, max(0, min(100, average + noise))))
                moment += timedelta(minutes=20)
            readings += [UsageLog(provider=status, quota_key=key, quota_label=key, used_percent=round(value, 2),
                                  observed_at=moment) for moment, value in values]
    UsageLog.objects.bulk_create(readings)


chatgpt = ProviderStatus.objects.get(provider='chatgpt')
claude = ProviderStatus.objects.get(provider='claude')
seed_history(chatgpt, CHATGPT)
seed_history(claude, CLAUDE)
ProviderStatus.objects.filter(pk=chatgpt.pk).update(
    collection_mode='api', state='ok', used_percent=CHATGPT['session'][-1], quota_label='Codex · ventana de 5 h',
    last_success_at=now - timedelta(minutes=4), last_attempt_at=now - timedelta(minutes=4), quotas=[
        {'key': 'session', 'label': 'Codex · ventana de 5 h', 'used_percent': str(CHATGPT['session'][-1]), 'reset_text': reset_text(timedelta(hours=3, minutes=12)), 'resets_at': iso(timedelta(hours=3, minutes=12))},
        {'key': 'weekly', 'label': 'Codex · semana', 'used_percent': str(CHATGPT['weekly'][-1]), 'reset_text': '', 'resets_at': CHATGPT_WEEK.isoformat()}])
ProviderCredential.objects.create(provider=chatgpt, secret='demo')
ProviderStatus.objects.filter(pk=claude.pk).update(
    collection_mode='client', state='ok', used_percent=CLAUDE['session'][-1], quota_label='Sesión de 5 horas',
    last_success_at=now - timedelta(minutes=4), last_attempt_at=now - timedelta(minutes=4), quotas=[
        {'key': 'session', 'label': 'Sesión de 5 horas', 'used_percent': str(CLAUDE['session'][-1]), 'reset_text': reset_text(timedelta(hours=1, minutes=48)), 'resets_at': iso(timedelta(hours=1, minutes=48))},
        {'key': 'weekly_all', 'label': 'Semana', 'used_percent': str(CLAUDE['weekly_all'][-1]), 'reset_text': '', 'resets_at': CLAUDE_WEEK.isoformat()}])

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

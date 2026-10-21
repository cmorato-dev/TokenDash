"""Render the real template/assets in Chromium without creating users or account data."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from django.db import connection
from django.test import RequestFactory
from django.test.utils import setup_test_environment, teardown_test_environment
from dashboard.views import DashboardView, HistoryView, StatusView
from playwright.sync_api import sync_playwright

# The check runs on its own test database, never on the deployment's data.
setup_test_environment()
old_config = connection.creation.create_test_db(verbosity=0)

factory = RequestFactory()
user = SimpleNamespace(is_authenticated=True, is_staff=True, username='Comprobación visual')
def call_view(view, path):
    request = factory.get(path)
    request.user = user
    response = view.as_view()(request)
    if hasattr(response, 'render'):
        response.render()
    return response.content

WEEKLY_RESET = '2030-10-27T06:41:46+00:00'


def renewal(moment):
    """«27/10 a las 7:41» in the dashboard's time zone, as the page should write it."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    local = datetime.fromisoformat(moment).astimezone(ZoneInfo(settings.TIME_ZONE))
    return f'{local.day}/{local.month} a las {local.hour}:{local.minute:02d}'


def seed():
    """A few readings so the history chart has something to draw."""
    from datetime import timedelta
    from django.utils import timezone
    from dashboard.models import ProviderStatus, UsageLog
    now = timezone.now()
    for provider in ('chatgpt', 'claude'):
        status = ProviderStatus.objects.get(provider=provider)
        for days_ago, value in [(0, 20), (0, 40), (2, 55), (20, 30), (60, 45), (200, 70), (400, 25)]:
            UsageLog.objects.create(provider=status, quota_key='session', quota_label='Sesión de 5 horas',
                                    used_percent=value, observed_at=now - timedelta(days=days_ago))
    # A weekly window as the providers publish it, to check the sentence under the gauge.
    ProviderStatus.objects.filter(provider='chatgpt').update(state='ok', last_success_at=now, quotas=[
        {'key': 'session', 'label': 'Codex · ventana de 5 h', 'used_percent': '1.00', 'reset_text': '', 'resets_at': '2030-01-01T00:00:00+00:00'},
        {'key': 'weekly', 'label': 'Codex · semana', 'used_percent': '26.00', 'reset_text': '', 'resets_at': WEEKLY_RESET}])
    return call_view(DashboardView, '/'), call_view(StatusView, '/api/status/'), call_view(HistoryView, '/api/history/')

html, status_json, _ = seed()
# The route handler runs in an async context: every period is prepared here.
history_json = {days: call_view(HistoryView, f'/api/history/?days={days}')
                for days in ('7', '30', '90', '182', '365', '1825')}
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1360, 'height': 1000}, device_scale_factor=1)
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route_request(route):
                path = urlparse(route.request.url).path
                if path.startswith('/static/'):
                    target = settings.STATIC_ROOT / path.removeprefix('/static/')
                    content_type = 'text/css' if path.endswith('.css') else 'application/javascript'
                    route.fulfill(body=target.read_bytes(), content_type=content_type)
                elif path == '/api/status/':
                    route.fulfill(body=status_json, content_type='application/json')
                elif path == '/api/history/':
                    # Answer with the period the page really asks for.
                    query = parse_qs(urlparse(route.request.url).query)
                    days = query.get('days', ['7'])[0]
                    route.fulfill(body=history_json.get(days, history_json['7']),
                                  content_type='application/json')
                elif path == '/':
                    route.fulfill(body=html, content_type='text/html')
                else:
                    route.fulfill(status=404)
            page.route('**/*', route_request)
            page.goto('http://tokendash.test/', wait_until='networkidle')
            assert page.locator('.provider-card').count() == 2
            # Works with or without stored data: a missing reading must show "—", never 0 %.
            assert all(text == '—' or text.endswith('%') for text in page.locator('.available').all_text_contents())
            weekly = page.locator('[data-provider=chatgpt] .extra-quotas p').first.inner_text()
            assert weekly == f'Llevas un 26% del límite esta semana. Se renueva el {renewal(WEEKLY_RESET)}.', weekly
            # The token section was removed on 21/10.
            assert page.locator('.token-card').count() == 0
            assert 'Tokens consumidos' not in page.content()
            # Every offered period must render a chart.
            for days in ('7', '30', '90', '182', '365', '1825'):
                page.select_option('#history-days', days)
                page.wait_for_timeout(500)
                assert page.locator('#history svg').count() >= 1, f'sin gráfico para {days} días'
                assert page.locator('#history-legend span').count() >= 1, f'sin leyenda para {days} días'
            assert not page.locator('#feedback').inner_text(), page.locator('#feedback').inner_text()
            assert page.locator('.provider-card').first.evaluate('(node) => getComputedStyle(node).borderRadius') == '20px'
            assert not errors, errors
            output = Path(os.getenv('TOKENDASH_ARTIFACTS', 'artifacts'))
            output.mkdir(parents=True, exist_ok=True)
            page.select_option('#history-days', '1825')
            page.wait_for_timeout(500)
            page.screenshot(path=str(output / 'dashboard-desktop.png'), full_page=True)
            page.select_option('#history-days', '90')
            page.wait_for_timeout(500)
            page.screenshot(path=str(output / 'dashboard-3-meses.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(output / 'dashboard-mobile.png'), full_page=True)
            print('OK: real templates, local CSS/JS, quota cards and history for every period; no browser errors.')
        finally:
            browser.close()
finally:
    connection.creation.destroy_test_db(old_config, verbosity=0)
    teardown_test_environment()

"""Render the real template/assets in Chromium without creating users or account data.

The dashboard is checked in English and in Spanish, each with its own script catalog.
"""
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
from django.utils import translation
from django.views.i18n import JavaScriptCatalog
from dashboard.views import DashboardView, HistoryView, StatusView
from playwright.sync_api import sync_playwright

# The check runs on its own test database, never on the deployment's data.
setup_test_environment()
old_config = connection.creation.create_test_db(verbosity=0)

factory = RequestFactory()
user = SimpleNamespace(is_authenticated=True, is_staff=True, username='Visual check')
def call_view(view, path):
    request = factory.get(path)
    request.user = user
    response = view.as_view()(request)
    if hasattr(response, 'render'):
        response.render()
    return response.content

WEEKLY_RESET = '2030-10-27T06:41:46+00:00'
# The sentence under the gauge, as each language should write it.
WEEKLY_SENTENCE = {
    'en': 'You have used 26% of the limit this week. It renews on {day_en} at {time}.',
    'es': 'Llevas un 26% del límite esta semana. Se renueva el {day_es} a las {time}.',
}


def renewal(moment, lang):
    """«Oct 27 at 07:41» or «27/10 a las 07:41» in the dashboard's time zone."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    local = datetime.fromisoformat(moment).astimezone(ZoneInfo(settings.TIME_ZONE))
    return WEEKLY_SENTENCE[lang].format(day_en=f'{local:%b} {local.day}', day_es=f'{local.day}/{local.month}',
                                        time=f'{local:%H:%M}')


def seed():
    """A few readings so the history chart has something to draw."""
    from datetime import timedelta
    from django.utils import timezone
    from dashboard.models import ProviderStatus, UsageLog
    now = timezone.now()
    for provider in ('chatgpt', 'claude'):
        status = ProviderStatus.objects.get(provider=provider)
        for days_ago, value in [(2, 55), (20, 30), (60, 45), (200, 70), (400, 25)]:
            UsageLog.objects.create(provider=status, quota_key='session', quota_label='5-hour session',
                                    used_percent=value, observed_at=now - timedelta(days=days_ago))
        # Two 5-hour cycles in one day: daily averaging must never hide these peaks.
        for minutes, value in [(600, 8), (480, 60), (360, 100), (300, 0), (180, 65), (60, 87)]:
            UsageLog.objects.create(provider=status, quota_key='session', quota_label='5-hour session',
                                    used_percent=value, observed_at=now - timedelta(minutes=minutes))
            UsageLog.objects.create(provider=status, quota_key='weekly' if provider == 'chatgpt' else 'weekly_all',
                                    quota_label='week', used_percent=90 - minutes / 100,
                                    observed_at=now - timedelta(minutes=minutes - 1))
    # A weekly window as the providers publish it, to check the sentence under the gauge.
    ProviderStatus.objects.filter(provider='chatgpt').update(state='ok', last_success_at=now, quotas=[
        {'key': 'session', 'label': 'Codex · 5 h window', 'used_percent': '1.00', 'reset_text': '', 'resets_at': '2030-01-01T00:00:00+00:00'},
        {'key': 'weekly', 'label': 'Codex · week', 'used_percent': '26.00', 'reset_text': '', 'resets_at': WEEKLY_RESET}])


def pages(lang):
    """Everything the page asks for, rendered before Playwright starts (it allows no queries)."""
    with translation.override(lang):
        return {
            'html': call_view(DashboardView, f'/{lang}/'),
            'catalog': JavaScriptCatalog.as_view()(factory.get(f'/{lang}/jsi18n/')).content,
            'status': call_view(StatusView, '/api/status/'),
            'history': {days: call_view(HistoryView, f'/api/history/?days={days}')
                        for days in ('1', '7', '30', '90', '182', '365', '1825')},
        }


seed()
rendered = {lang: pages(lang) for lang in ('en', 'es')}
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for lang, answers in rendered.items():
                # One handler per language: the loop variables are read when the page loads.
                page = browser.new_page(viewport={'width': 1360, 'height': 1000}, device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route_request(route):
                    path = urlparse(route.request.url).path
                    if path.startswith('/static/'):
                        target = settings.STATIC_ROOT / path.removeprefix('/static/')
                        content_type = 'text/css' if path.endswith('.css') else 'application/javascript'
                        route.fulfill(body=target.read_bytes(), content_type=content_type)
                    elif path == f'/{lang}/jsi18n/':
                        route.fulfill(body=answers['catalog'], content_type='text/javascript')
                    elif path == '/api/status/':
                        route.fulfill(body=answers['status'], content_type='application/json')
                    elif path == '/api/history/':
                        # Answer with the period the page really asks for.
                        days = parse_qs(urlparse(route.request.url).query).get('days', ['7'])[0]
                        route.fulfill(body=answers['history'].get(days, answers['history']['7']),
                                      content_type='application/json')
                    elif path == f'/{lang}/':
                        route.fulfill(body=answers['html'], content_type='text/html')
                    else:
                        route.fulfill(status=404)
                page.route('**/*', route_request)
                page.goto(f'http://tokendash.test/{lang}/', wait_until='networkidle')
                assert page.locator('.provider-card').count() == 2
                # Works with or without stored data: a missing reading must show "—", never 0 %.
                assert all(text == '—' or text.endswith('%') for text in page.locator('.available').all_text_contents())
                weekly = page.locator('[data-provider=chatgpt] .extra-quotas p').first.inner_text()
                assert weekly == renewal(WEEKLY_RESET, lang), weekly
                # The token section was removed on 21/10.
                assert page.locator('.token-card').count() == 0
                # Every offered period must render a chart.
                for days in ('1', '7', '30', '90', '182', '365', '1825'):
                    page.select_option('#history-days', days)
                    page.wait_for_timeout(500)
                    assert page.locator('#history svg').count() >= 1, f'{lang}: no chart for {days} days'
                    assert page.locator('#history-legend span').count() >= 1, f'{lang}: no legend for {days} days'
                assert not page.locator('#feedback').inner_text(), page.locator('#feedback').inner_text()
                assert page.locator('.provider-card').first.evaluate('(node) => getComputedStyle(node).borderRadius') == '20px'
                assert page.locator('.language-switch [aria-current]').inner_text() == lang.upper()
                assert not errors, errors
                output = Path(os.getenv('TOKENDASH_ARTIFACTS', 'artifacts'))
                output.mkdir(parents=True, exist_ok=True)
                page.select_option('#history-days', '1')
                page.wait_for_timeout(500)
                assert page.locator('#history .hour-tick').count() >= 7
                titles = page.locator('#history circle title').all_text_contents()
                assert any('100%' in title for title in titles)
                assert any('87%' in title for title in titles)
                paths = page.locator('#history path').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("d"))')
                assert any(path.count('L') >= 5 for path in paths), paths
                # Real timestamps preserve both two-hour and one-hour intervals.
                xs = page.locator('#history circle').evaluate_all('(nodes) => nodes.slice(0, 6).map(n => Number(n.getAttribute("cx")))')
                assert abs((xs[1] - xs[0]) / (xs[4] - xs[3]) - 1) < 0.001, xs
                assert abs((xs[2] - xs[1]) / (xs[3] - xs[2]) - 2) < 0.001, xs
                assert ':' in titles[-1], titles[-1]
                assert page.locator('#history-legend > span').count() == 4
                page.screenshot(path=str(output / f'dashboard-24-hours-{lang}.png'), full_page=True)
                page.select_option('#history-days', '7')
                page.wait_for_timeout(500)
                assert page.locator('#history .day-boundary').count() == 7
                paths = page.locator('#history path').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("d"))')
                assert any(path.count('M') == 2 for path in paths), paths
                page.screenshot(path=str(output / f'dashboard-desktop-{lang}.png'), full_page=True)
                page.select_option('#history-days', '90')
                page.wait_for_timeout(500)
                page.screenshot(path=str(output / f'dashboard-3-months-{lang}.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.select_option('#history-days', '1')
                page.wait_for_timeout(500)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output / f'dashboard-mobile-{lang}.png'), full_page=True)
                page.close()
            print('OK: real templates, local CSS/JS, quota cards and history for every period, '
                  'in English and Spanish; no browser errors.')
        finally:
            browser.close()
finally:
    connection.creation.destroy_test_db(old_config, verbosity=0)
    teardown_test_environment()

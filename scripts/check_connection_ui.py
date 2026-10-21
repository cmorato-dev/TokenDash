"""Render the real admin template and test the Claude guide in a browser, offline, in both languages."""
import mimetypes
import os
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory
from django.test.utils import setup_test_environment, teardown_test_environment
from django.utils import translation
from django.views.i18n import JavaScriptCatalog
from scraper.connection_views import connections
from playwright.sync_api import sync_playwright, expect

# The check runs on its own test database, never on the deployment's data.
setup_test_environment()
old_config = connection.creation.create_test_db(verbosity=0)
admin = get_user_model().objects.create_superuser('admin-visual', password='test-only-password')

# What each language must show and copy.
EXPECTED = {
    'en': {'state': 'Not signed in', 'ssh': 'ssh user@tokendash-server', 'title': 'Link Claude with the TokenDash server',
           'copy': 'Copy', 'copied': 'Copied'},
    'es': {'state': 'Sin sesión iniciada', 'ssh': 'ssh usuario@servidor-tokendash', 'title': 'Vincular Claude con el servidor TokenDash',
           'copy': 'Copiar', 'copied': 'Copiado'},
}


def render(lang):
    request = RequestFactory().get(f'/{lang}/admin/connect/')
    request.user = admin
    request.session = {}
    # The worker has not published the session state yet: the page must say so
    # and name the command to run.
    with translation.override(lang), patch('scraper.claude_client_views.client_session_state', return_value={
            'installed': True, 'connected': False, 'method': 'none', 'checked_at': None,
            'label': EXPECTED[lang]['state'],
            'command': 'docker compose exec worker claude auth login',
            'status_command': 'docker compose exec worker claude auth status',
            'check_command': 'docker compose exec worker python manage.py claude_status'}):
        return connections(request).content, JavaScriptCatalog.as_view()(RequestFactory().get(f'/{lang}/jsi18n/')).content


rendered = {lang: render(lang) for lang in EXPECTED}
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for lang, (html, catalog) in rendered.items():
                expected = EXPECTED[lang]
                context = browser.new_context(viewport={'width': 1440, 'height': 1100})
                page = context.new_page()
                # The intranet serves plain HTTP, where navigator.clipboard does not exist:
                # record what the page's fallback copies.
                page.add_init_script("""
                  const copy = document.execCommand.bind(document);
                  document.execCommand = command => {
                    if (command === 'copy') window.__copied = [...document.querySelectorAll('body > textarea')].pop()?.value;
                    return copy(command);
                  };""")
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route_request(route):
                    path = urlparse(route.request.url).path
                    if path.startswith('/static/'):
                        target = settings.STATIC_ROOT / path.removeprefix('/static/')
                        route.fulfill(body=target.read_bytes(), content_type=(mimetypes.guess_type(path)[0] or 'application/octet-stream') + '; charset=utf-8')
                    elif path == f'/{lang}/jsi18n/':
                        route.fulfill(body=catalog, content_type='text/javascript; charset=utf-8')
                    else:
                        route.fulfill(body=html, content_type='text/html; charset=utf-8')
                page.route('**/*', route_request)
                page.goto(f'http://tokendash.test/{lang}/admin/connect/', wait_until='networkidle')
                # A deployment without a session must find the guide open, with every command.
                card = page.locator('#claude-card')
                expect(card).to_contain_text(expected['state'])
                expect(page.locator('details.claude-guide')).to_have_attribute('open', '')
                commands = page.locator('#claude-guide-steps code.command').all_text_contents()
                assert commands == [expected['ssh'], 'cd ~/tokendash',
                                    'docker compose exec worker claude auth status',
                                    'docker compose exec worker claude auth login',
                                    'docker compose exec worker python manage.py claude_status'], commands
                page.locator('#claude-guide-steps .copy-command').nth(3).click()
                assert page.evaluate('window.__copied') == 'docker compose exec worker claude auth login', page.evaluate('window.__copied')
                expect(page.locator('#claude-guide-steps .copy-command').nth(3)).to_have_text(expected['copied'])
                page.locator('#claude-guide-copy').click()
                guide = page.evaluate('window.__copied')
                assert guide.startswith(expected['title']), guide[:80]
                assert '\n    docker compose exec worker python manage.py claude_status' in guide, guide
                # The Copy buttons are not part of the copied text.
                assert not any(line.rstrip().endswith((expected['copy'], expected['copied'])) for line in guide.splitlines()), guide
                body = page.locator('body').inner_text()
                for removed in ('Other options', 'Chrome extension', 'PC agent', 'server browser',
                                'Otras opciones', 'Extensión para Chrome', 'Agente del PC', 'navegador del servidor'):
                    assert removed not in body, removed
                assert not errors, errors
                output = Path(os.getenv('TOKENDASH_ARTIFACTS', 'artifacts'))
                output.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output / f'connections-admin-{lang}.png'), full_page=True)
                context.close()
            print('OK: real admin page in English and Spanish, local assets, Claude guide open with its five '
                  'commands in order, copy buttons, full guide copy, no removed sections, no JavaScript errors.')
        finally:
            browser.close()
finally:
    connection.creation.destroy_test_db(old_config, verbosity=0)
    teardown_test_environment()

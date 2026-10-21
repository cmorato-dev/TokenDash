import base64
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import ProviderStatus, UsageLog
from . import codex_oauth
from .models import ProviderCredential
from .tasks import claim_refresh, refresh_provider


def jwt(claims):
    encode = lambda data: base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()
    return f"{encode({'alg': 'none'})}.{encode(claims)}.signature"


def token_response(minutes=60, refresh='refresh-1'):
    auth = {'https://api.openai.com/auth': {'chatgpt_account_id': 'acct-1', 'chatgpt_plan_type': 'plus'}}
    return {'access_token': jwt({'exp': int((timezone.now() + timedelta(minutes=minutes)).timestamp()), **auth}),
            'refresh_token': refresh, 'id_token': jwt(auth)}


USAGE = {'plan_type': 'plus', 'rate_limit': {'allowed': True, 'limit_reached': False,
         'primary_window': {'used_percent': 42, 'limit_window_seconds': 18000, 'reset_after_seconds': 100, 'reset_at': 1792496506},
         'secondary_window': {'used_percent': 7, 'limit_window_seconds': 604800, 'reset_after_seconds': 100, 'reset_at': 1793083306}}}


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CodexLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('codex-admin', password='test-only-password')
        self.client.force_login(self.user)
        self.url = reverse('scraper_codex_login')
        self.status = ProviderStatus.objects.get(provider='chatgpt')

    def post(self, **payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

    def start(self):
        url = self.post(action='start').json()['url']
        return parse_qs(urlparse(url).query)

    def test_start_uses_pkce_and_state(self):
        query = self.start()
        self.assertEqual(query['client_id'], [codex_oauth.CLIENT_ID])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['redirect_uri'], [codex_oauth.REDIRECT_URI])
        pending = self.client.session['codex_oauth_login']
        self.assertEqual(query['state'], [pending['state']])
        self.assertNotIn(pending['verifier'], json.dumps(query))

    def test_superuser_and_csrf_required(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, data='{"action":"start"}', content_type='application/json').status_code, 403)
        staff = get_user_model().objects.create_user('staff', password='test-only-password', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.post(action='start').status_code, 403)

    @patch('scraper.codex_views.enqueue_refresh')
    @patch('scraper.codex_oauth.http_json')
    def test_complete_stores_encrypted_tokens_and_switches_to_api(self, http, enqueue):
        state = self.start()['state'][0]
        http.return_value = (200, token_response())
        response = self.post(action='complete', callback=f'http://localhost:1455/auth/callback?code=abc&scope=openid&state={state}')
        self.assertEqual(response.status_code, 200, response.content)
        form = http.call_args.kwargs['form']
        self.assertEqual(form['code'], 'abc')
        self.assertEqual(form['grant_type'], 'authorization_code')
        credential = ProviderCredential.objects.get(provider=self.status)
        self.assertNotIn('refresh-1', credential.secret)
        self.assertEqual(codex_oauth.decrypt(credential.secret)['refresh_token'], 'refresh-1')
        self.assertEqual(credential.plan_type, 'plus')
        self.status.refresh_from_db()
        self.assertEqual(self.status.collection_mode, 'api')
        enqueue.assert_called_once_with(self.status.pk)
        self.assertNotIn('codex_oauth_login', self.client.session)

    @patch('scraper.codex_oauth.http_json')
    def test_wrong_state_bad_url_and_expired_login_rejected(self, http):
        self.start()
        self.assertEqual(self.post(action='complete', callback='http://localhost:1455/auth/callback?code=abc&state=other').status_code, 400)
        self.assertEqual(self.post(action='complete', callback='https://evil.example/auth/callback?code=a&state=b').status_code, 400)
        session = self.client.session
        session['codex_oauth_login']['created'] = (timezone.now() - timedelta(hours=1)).isoformat()
        session.save()
        self.assertEqual(self.post(action='complete', callback='code=a&state=b').status_code, 409)
        http.assert_not_called()
        self.assertFalse(ProviderCredential.objects.exists())

    def test_disconnect_deletes_credential(self):
        codex_oauth.save_credential(self.status, codex_oauth.tokens_from_response(token_response()))
        ProviderStatus.objects.filter(pk=self.status.pk).update(collection_mode='api')
        self.assertEqual(self.post(action='disconnect').status_code, 200)
        self.assertFalse(ProviderCredential.objects.exists())
        self.assertEqual(ProviderStatus.objects.get(pk=self.status.pk).collection_mode, 'none')


class CodexPollTests(TestCase):
    def setUp(self):
        self.status = ProviderStatus.objects.get(provider='chatgpt')
        ProviderStatus.objects.filter(pk=self.status.pk).update(collection_mode='api')

    def connect(self, minutes=60):
        codex_oauth.save_credential(self.status, codex_oauth.tokens_from_response(token_response(minutes)))

    def run_refresh(self):
        token = claim_refresh(self.status.pk)
        self.assertTrue(token)
        refresh_provider(self.status.pk, token)
        return ProviderStatus.objects.get(pk=self.status.pk)

    @patch('scraper.codex_oauth.http_json')
    def test_usage_windows_become_separate_quotas(self, http):
        self.connect()
        http.return_value = (200, USAGE)
        status = self.run_refresh()
        self.assertEqual(status.state, 'ok')
        self.assertEqual(float(status.used_percent), 42)
        self.assertEqual([(q['key'], q['used_percent']) for q in status.quotas], [('session', '42.00'), ('weekly', '7.00')])
        self.assertIn('resets_at', status.quotas[0])
        self.assertTrue(status.quotas[0]['reset_text'].startswith('Se reinicia'))
        self.assertEqual(UsageLog.objects.filter(provider=status).count(), 2)
        headers = http.call_args.kwargs['headers']
        self.assertEqual(headers['ChatGPT-Account-Id'], 'acct-1')
        self.assertTrue(headers['Authorization'].startswith('Bearer '))

    @patch('scraper.codex_oauth.http_json')
    def test_expired_access_token_is_refreshed_and_rotated_token_saved(self, http):
        self.connect(minutes=-5)
        http.side_effect = [(200, token_response(refresh='refresh-2')), (200, USAGE)]
        status = self.run_refresh()
        self.assertEqual(status.state, 'ok')
        self.assertEqual(http.call_args_list[0].kwargs['body']['grant_type'], 'refresh_token')
        secret = ProviderCredential.objects.get(provider=self.status).secret
        self.assertEqual(codex_oauth.decrypt(secret)['refresh_token'], 'refresh-2')

    @patch('scraper.codex_oauth.http_json')
    def test_revoked_login_marks_expired_and_keeps_last_reading(self, http):
        self.connect()
        http.return_value = (200, USAGE)
        self.run_refresh()
        http.side_effect = [(401, None), (401, {'error': 'invalid_grant'})]
        status = self.run_refresh()
        self.assertEqual(status.state, 'expired')
        self.assertEqual(float(status.used_percent), 42)
        self.assertIn('Conectar cuentas', status.last_error)

    @patch('scraper.codex_oauth.http_json')
    def test_blocked_or_unexpected_responses_are_sanitized(self, http):
        self.connect()
        http.return_value = (403, None)
        status = self.run_refresh()
        self.assertEqual(status.state, 'blocked')
        http.return_value = (200, {'rate_limit': None})
        status = self.run_refresh()
        self.assertEqual(status.state, 'unavailable')
        self.assertIsNone(status.used_percent)

    def test_changed_secret_key_requires_new_login(self):
        self.connect()
        with override_settings(SECRET_KEY='another-secret-key'):
            status = self.run_refresh()
        self.assertEqual(status.state, 'expired')

    def test_invalid_windows_are_ignored(self):
        readings = codex_oauth.readings_from_windows([
            {'used_percent': 120, 'window_minutes': 300}, {'used_percent': True, 'window_minutes': 300},
            {'used_percent': 'x', 'window_minutes': 300}, {'used_percent': 5, 'window_minutes': 0},
            {'used_percent': 12.5, 'window_minutes': 10080},
        ])
        self.assertEqual([(r.key, str(r.used_percent)) for r in readings], [('weekly', '12.50')])

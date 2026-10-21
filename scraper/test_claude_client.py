"""The server-side Claude quota reader must never invent a percentage."""
import json
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from scraper import claude_client
from scraper.quotas import claude_readings


class ClaudeClientTests(SimpleTestCase):
    def windows(self, **extra):
        """The shape the probe returns once the client has answered."""
        payload = {'five_hour': {'used_percentage': 42, 'resets_at': '2026-10-20T21:00:00Z'},
                   'seven_day': {'used_percentage': 7, 'resets_at': None}}
        payload.update(extra)
        return payload

    def test_reads_only_the_published_windows(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client.helper(), 'probe', return_value={
                 'ok': True, 'available': True, 'windows': self.windows()}):
            windows = claude_client.read_limits()
        self.assertEqual(sorted(windows), ['five_hour', 'seven_day'])
        self.assertEqual(windows['five_hour']['used_percentage'], 42)

    def test_a_failing_client_keeps_the_previous_reading(self):
        for answer in ({'ok': False, 'stage': 'initialize'}, {'ok': True, 'available': False, 'windows': {}},
                       {'ok': True, 'available': True, 'windows': {}}):
            with patch.object(claude_client, 'find_executable', return_value='claude'), \
                 patch.object(claude_client.helper(), 'probe', return_value=answer), \
                 patch.object(claude_client, 'auth_state', return_value=None):
                with self.assertRaises(claude_client.ClientUnavailable):
                    claude_client.read_limits()

    def test_the_error_names_the_credential_that_cannot_read_the_quota(self):
        """A setup-token is scoped to model requests: say so instead of a generic text."""
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client.helper(), 'probe', return_value={
                 'ok': True, 'available': False, 'windows': {}}), \
             patch.object(claude_client, 'auth_state', return_value='oauth_token'):
            with self.assertRaises(claude_client.ClientUnavailable) as caught:
                claude_client.read_limits()
        self.assertIn('setup-token', caught.exception.message)
        self.assertIn('claude auth login', caught.exception.message)

    def test_the_error_mentions_a_missing_session(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client.helper(), 'probe', return_value={
                 'ok': True, 'available': False, 'windows': {}}), \
             patch.object(claude_client, 'auth_state', return_value='none'):
            with self.assertRaises(claude_client.ClientUnavailable) as caught:
                claude_client.read_limits()
        self.assertIn('claude auth login', caught.exception.message)

    def test_an_api_key_is_not_a_subscription_credential(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client.helper(), 'probe', return_value={
                 'ok': True, 'available': False, 'windows': {}}), \
             patch.object(claude_client, 'auth_state', return_value='api_key'):
            with self.assertRaises(claude_client.ClientUnavailable) as caught:
                claude_client.read_limits()
        self.assertIn('clave de API', caught.exception.message)

    def test_a_missing_client_is_reported_without_reading_anything(self):
        with patch.object(claude_client, 'find_executable', return_value=None):
            with self.assertRaises(claude_client.ClientUnavailable):
                claude_client.read_limits()

    def test_client_errors_never_expose_the_client_output(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client.helper(), 'probe', side_effect=RuntimeError('private token leaked')):
            with self.assertRaises(claude_client.ClientUnavailable) as caught:
                claude_client.read_limits()
        self.assertNotIn('private token leaked', str(caught.exception))

    def test_readings_map_claude_windows_to_the_dashboard_labels(self):
        readings = claude_readings([
            {'name': 'five_hour', 'used_percentage': 42, 'resets_at': claude_client.epoch('2026-10-20T21:00:00Z')},
            {'name': 'seven_day', 'used_percentage': 7, 'resets_at': None},
        ])
        self.assertEqual([r.key for r in readings], ['session', 'weekly_all'])
        self.assertEqual([str(r.used_percent) for r in readings], ['42.00', '7.00'])
        self.assertIn('Se reinicia el', readings[0].reset_text)

    def test_out_of_range_or_unknown_windows_are_dropped(self):
        readings = claude_readings([
            {'name': 'five_hour', 'used_percentage': 101, 'resets_at': None},
            {'name': 'seven_day_oauth_apps', 'used_percentage': 50, 'resets_at': None},
        ])
        self.assertEqual(readings, [])

    def test_epoch_accepts_only_iso_instants(self):
        self.assertIsNone(claude_client.epoch(None))
        self.assertIsNone(claude_client.epoch('not-a-date'))
        self.assertIsNotNone(claude_client.epoch('2026-10-20T21:00:00Z'))

    def test_the_server_uses_the_shared_protocol_helper(self):
        """One implementation of the protocol: the server must not fork it."""
        self.assertEqual(claude_client.HELPER, settings.BASE_DIR / 'scraper' / 'claude_usage.py')
        self.assertTrue(claude_client.HELPER.is_file())
        source = claude_client.HELPER.read_text(encoding='utf-8')
        self.assertIn("'subtype': 'get_usage'", source)
        self.assertIn('skip_behaviors', source)
        # No user message is ever sent to the model.
        self.assertNotIn("'type': 'user'", source)


class ClaudeSessionStateTests(SimpleTestCase):
    """The admin panel reports the kind of credential, never the credential."""

    def test_a_claude_ai_session_can_read_the_quota(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client, 'auth_state', return_value='claude.ai'):
            state = claude_client.session_state()
        self.assertTrue(state['connected'])
        self.assertEqual(state['method'], 'claude.ai')
        self.assertIn('claude auth login', state['command'])
        self.assertIn('auth status', state['status_command'])

    def test_a_setup_token_is_reported_as_unable_to_read_the_quota(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client, 'auth_state', return_value='oauth_token'):
            state = claude_client.session_state()
        self.assertFalse(state['connected'])
        self.assertIn('setup-token', state['label'])

    def test_no_session_is_reported_as_not_connected(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client, 'auth_state', return_value='none'):
            state = claude_client.session_state()
        self.assertFalse(state['connected'])
        self.assertEqual(state['method'], 'none')

    def test_an_unreadable_status_does_not_claim_that_there_is_no_session(self):
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client, 'auth_state', return_value=None):
            state = claude_client.session_state()
        self.assertFalse(state['connected'])
        self.assertEqual(state['method'], 'unknown')
        self.assertIn('No se ha podido comprobar', state['label'])

    def test_a_missing_client_is_reported_without_running_anything(self):
        with patch.object(claude_client, 'find_executable', return_value=None):
            state = claude_client.session_state()
        self.assertFalse(state['installed'])
        self.assertFalse(state['connected'])
        self.assertEqual(state['method'], 'unavailable')

    def test_the_session_state_never_exposes_the_credential(self):
        """Only the kind of credential may be published."""
        with patch.object(claude_client, 'find_executable', return_value='claude'), \
             patch.object(claude_client, 'auth_state', return_value='claude.ai'):
            state = claude_client.session_state()
        self.assertEqual(sorted(state), ['command', 'connected', 'installed', 'label', 'method', 'status_command'])
        self.assertNotIn('token', state['label'].lower())


class ClaudeClientProbeTests(SimpleTestCase):
    """The probe must only send control requests, never a model turn."""

    def test_only_control_requests_leave_the_client(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('claude_usage_probe', claude_client.HELPER)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        sent = []

        class FakeProcess:
            def __init__(self):
                self.stdin = FakeStdin(sent)
                self.stdout = FakeStdout()
                self.returncode = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                self.returncode = 0

        class FakeStdin:
            def __init__(self, sink):
                self.sink = sink

            def write(self, text):
                self.sink.append(json.loads(text))

            def flush(self):
                pass

            def close(self):
                pass

        class FakeStdout:
            def __iter__(self):
                yield json.dumps({'type': 'control_response', 'response': {
                    'subtype': 'success', 'request_id': 'initialize', 'response': {}}})
                yield json.dumps({'type': 'control_response', 'response': {
                    'subtype': 'success', 'request_id': 'usage',
                    'response': {'rate_limits_available': True,
                                 'rate_limits': {'five_hour': {'utilization': 12, 'resets_at': None},
                                                 'seven_day': {'utilization': 34, 'resets_at': None}}}}})

            def close(self):
                pass

        with patch.object(helper.subprocess, 'Popen', return_value=FakeProcess()):
            result = helper.probe('official-client')
        self.assertEqual([row['type'] for row in sent], ['control_request', 'control_request'])
        self.assertEqual(sent[1]['request'], {'subtype': 'get_usage', 'skip_behaviors': True})
        self.assertEqual(result['windows']['seven_day']['used_percentage'], 34)

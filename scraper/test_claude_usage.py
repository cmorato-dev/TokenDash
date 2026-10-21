"""The quota probe must never submit a model turn or expose raw client output."""
import importlib.util
import io
import json
import threading
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase


spec = importlib.util.spec_from_file_location('claude_usage_test', settings.BASE_DIR / 'scraper/claude_usage.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ClaudeUsageTests(SimpleTestCase):
    def process(self, data):
        process = Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO('\n'.join(json.dumps(row) for row in [
            {'type': 'system', 'private': 'NOT_FOR_DASHBOARD'},
            {'type': 'control_response', 'response': {'subtype': 'success', 'request_id': 'initialize', 'response': {}}},
            {'type': 'control_response', 'response': {'subtype': 'success', 'request_id': 'usage', 'response': data}},
        ]) + '\n')
        process.poll.return_value = 0
        # Keep the recorded request stream readable after cleanup.
        process.stdin.close = Mock()
        return process

    def test_only_control_requests_and_whitelisted_windows_leave_the_client(self):
        process = self.process({'rate_limits_available': True, 'email': 'PRIVATE', 'behaviors': {'private': 'PRIVATE'},
                                'rate_limits': {'five_hour': {'utilization': 58, 'resets_at': '2026-10-20T18:00:00Z'},
                                                'seven_day': {'utilization': 31, 'resets_at': None},
                                                'private': 'PRIVATE'}})
        with patch.object(helper.subprocess, 'Popen', return_value=process) as spawn:
            result = helper.probe('official-client')
        requests = [json.loads(row) for row in process.stdin.getvalue().splitlines()]
        self.assertEqual([r['type'] for r in requests], ['control_request', 'control_request'])
        self.assertEqual(requests[1]['request'], {'subtype': 'get_usage', 'skip_behaviors': True})
        self.assertEqual(result['windows']['five_hour']['used_percentage'], 58)
        self.assertNotIn('PRIVATE', json.dumps(result))
        command = spawn.call_args.args[0]
        self.assertIn('--no-session-persistence', command)
        self.assertIn('{"disableAllHooks":true}', command)
        self.assertNotIn('/usage', command)  # No string prompt that a model could interpret.

    def test_invalid_or_unknown_values_cannot_become_zero_usage(self):
        process = self.process({'rate_limits_available': False, 'rate_limits': {
            'five_hour': {'utilization': True}, 'seven_day': {'utilization': 101}}})
        with patch.object(helper.subprocess, 'Popen', return_value=process):
            result = helper.probe('official-client')
        self.assertEqual(result, {'ok': True, 'available': False, 'subscription_type': None, 'windows': {}})

    def test_the_subscription_type_is_reported_to_tell_the_credential_apart(self):
        """A setup-token and a claude.ai session both answer; only one publishes quotas."""
        process = self.process({'rate_limits_available': False, 'subscription_type': 'max'})
        with patch.object(helper.subprocess, 'Popen', return_value=process):
            result = helper.probe('official-client')
        self.assertEqual(result['subscription_type'], 'max')
        self.assertFalse(result['available'])

    def test_a_non_text_subscription_type_is_dropped(self):
        process = self.process({'rate_limits_available': False, 'subscription_type': {'private': 'PRIVATE'}})
        with patch.object(helper.subprocess, 'Popen', return_value=process):
            result = helper.probe('official-client')
        self.assertIsNone(result['subscription_type'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_client_exits_before_answer_without_exposing_errors(self):
        process = Mock(stdin=io.StringIO(), stdout=io.StringIO('not-json\n'))
        process.poll.return_value = 0
        with patch.object(helper.subprocess, 'Popen', return_value=process):
            result = helper.probe('official-client')
        self.assertEqual(result, {'ok': False, 'stage': 'initialize'})

    def test_hung_client_is_terminated_at_the_deadline(self):
        stopped = threading.Event()

        class WaitingOutput:
            def __iter__(self):
                yield json.dumps({'type': 'control_response', 'response': {
                    'subtype': 'success', 'request_id': 'initialize', 'response': {}}})
                stopped.wait(2)

            def close(self):
                stopped.set()

        process = Mock(stdin=io.StringIO(), stdout=WaitingOutput())
        process.poll.return_value = None
        process.terminate.side_effect = stopped.set
        with patch.object(helper.subprocess, 'Popen', return_value=process):
            result = helper.probe('official-client', timeout=.05)
        self.assertEqual(result, {'ok': False, 'stage': 'usage'})
        process.terminate.assert_called_once()

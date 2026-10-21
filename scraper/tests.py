from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from dashboard.models import ProviderStatus, UsageLog
from .quotas import QuotaReading, SessionExpired
from .tasks import claim_refresh, enqueue_refresh, refresh_all, refresh_provider

class TaskTests(TestCase):
    def setUp(self):
        self.provider = ProviderStatus.objects.get(provider='chatgpt')
        self.provider.collection_mode = 'api'
        self.provider.save(update_fields=['collection_mode'])

    def test_an_unconnected_provider_is_never_refreshed(self):
        ProviderStatus.objects.filter(pk=self.provider.pk).update(collection_mode='none')
        self.assertIsNone(claim_refresh(self.provider.pk))

    @patch('scraper.codex_oauth.poll')
    def test_success_writes_all_quotas_once(self, scrape):
        scrape.return_value = [QuotaReading('session', 'Sesión', Decimal('30')), QuotaReading('weekly', 'Semana', Decimal('70'))]
        token = claim_refresh(self.provider.pk)
        self.assertIsNone(claim_refresh(self.provider.pk))
        refresh_provider(self.provider.pk, token)
        refresh_provider(self.provider.pk, token)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.used_percent, 30)
        self.assertEqual(self.provider.state, 'ok')
        self.assertEqual(UsageLog.objects.count(), 2)
        self.assertEqual(scrape.call_count, 1)

    @patch('scraper.codex_oauth.poll')
    def test_duplicate_inflight_delivery_is_ignored(self, scrape):
        token = claim_refresh(self.provider.pk)
        self.provider.refresh_from_db()
        self.provider.last_attempt_at = timezone.now()
        self.provider.save()
        refresh_provider(self.provider.pk, token)
        scrape.assert_not_called()

    @patch('scraper.codex_oauth.poll', side_effect=SessionExpired())
    def test_failure_preserves_latest_success(self, scrape):
        before = timezone.now() - timedelta(days=1)
        self.provider.used_percent = 45
        self.provider.last_success_at = before
        self.provider.save()
        refresh_provider(self.provider.pk, claim_refresh(self.provider.pk))
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.used_percent, 45)
        self.assertEqual(self.provider.last_success_at, before)
        self.assertEqual(self.provider.state, 'expired')
        self.assertEqual(self.provider.consecutive_failures, 1)
        self.assertFalse(UsageLog.objects.exists())

    @patch('scraper.codex_oauth.poll', side_effect=RuntimeError('secret-cookie-content'))
    def test_unexpected_error_is_sanitized(self, scrape):
        refresh_provider(self.provider.pk, claim_refresh(self.provider.pk))
        self.provider.refresh_from_db()
        self.assertNotIn('secret-cookie-content', self.provider.last_error)
        self.assertEqual(self.provider.state, 'error')

    @patch('scraper.tasks.refresh_provider.apply_async', side_effect=ConnectionError())
    def test_queue_failure_releases_lease(self, queue):
        with self.assertRaises(ConnectionError):
            enqueue_refresh(self.provider.pk)
        self.assertIsNotNone(claim_refresh(self.provider.pk))

    @patch('scraper.codex_oauth.poll')
    def test_expired_lease_is_recoverable_and_old_worker_ignored(self, scrape):
        stale = claim_refresh(self.provider.pk)
        ProviderStatus.objects.filter(pk=self.provider.pk).update(refresh_expires_at=timezone.now() - timedelta(seconds=1))
        new = claim_refresh(self.provider.pk)
        self.assertNotEqual(stale, new)
        refresh_provider(self.provider.pk, stale)
        scrape.assert_not_called()

    def test_database_rejects_out_of_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderStatus.objects.filter(pk=self.provider.pk).update(used_percent=101)

class ClaudeClientTaskTests(TestCase):
    """The server reads Claude's limits with the official client, without a PC."""

    def setUp(self):
        self.provider = ProviderStatus.objects.get(provider='claude')
        self.provider.collection_mode = 'client'
        self.provider.save(update_fields=['collection_mode'])

    def test_a_reading_updates_the_provider_and_the_history(self):
        with patch('scraper.claude_client.read_limits', return_value={
                'five_hour': {'used_percentage': 42, 'resets_at': '2026-10-20T21:00:00Z'},
                'seven_day': {'used_percentage': 7, 'resets_at': None}}):
            token = claim_refresh(self.provider.pk)
            refresh_provider(self.provider.pk, token)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.state, 'ok')
        self.assertEqual(str(self.provider.used_percent), '42.00')
        self.assertEqual([q['key'] for q in self.provider.quotas], ['session', 'weekly_all'])
        self.assertEqual(UsageLog.objects.filter(provider=self.provider).count(), 2)

    def test_a_failing_client_keeps_the_last_valid_reading(self):
        UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='Sesión',
                                used_percent=Decimal('30'), observed_at=timezone.now())
        self.provider.used_percent = Decimal('30')
        self.provider.quota_label = 'Sesión de 5 horas'
        self.provider.last_success_at = timezone.now() - timedelta(hours=1)
        self.provider.save()
        from scraper.claude_client import ClientUnavailable
        with patch('scraper.claude_client.read_limits', side_effect=ClientUnavailable()):
            token = claim_refresh(self.provider.pk)
            refresh_provider(self.provider.pk, token)
        self.provider.refresh_from_db()
        self.assertEqual(str(self.provider.used_percent), '30.00')
        self.assertEqual(self.provider.state, 'unavailable')
        self.assertTrue(self.provider.last_success_at)

    def test_refresh_all_includes_the_client_mode(self):
        with patch('scraper.tasks.refresh_provider.apply_async') as queue:
            refresh_all()
        queued = [call.kwargs['args'][0] for call in queue.call_args_list if 'args' in call.kwargs]
        self.assertIn(self.provider.pk, queued)

    def test_the_worker_publishes_the_kind_of_credential(self):
        """The panel cannot run the client: the worker publishes the answer."""
        from scraper.tasks import publish_client_auth_method
        with patch('scraper.claude_client.current_auth_method', return_value='claude.ai'):
            method = publish_client_auth_method()
        self.provider.refresh_from_db()
        self.assertEqual(method, 'claude.ai')
        self.assertEqual(self.provider.client_auth_method, 'claude.ai')
        self.assertIsNotNone(self.provider.client_auth_checked_at)

    def test_the_published_record_never_holds_the_credential(self):
        from scraper.tasks import publish_client_auth_method
        with patch('scraper.claude_client.current_auth_method', return_value='oauth_token'):
            publish_client_auth_method()
        self.provider.refresh_from_db()
        # Only the kind of credential, never the token itself.
        self.assertEqual(self.provider.client_auth_method, 'oauth_token')
        self.assertNotIn('sk-', self.provider.client_auth_method)

    def test_reading_the_limits_also_publishes_the_session_state(self):
        with patch('scraper.claude_client.current_auth_method', return_value='claude.ai'), \
             patch('scraper.claude_client.read_limits', return_value={
                 'five_hour': {'used_percentage': 42, 'resets_at': '2026-10-20T21:00:00Z'}}):
            token = claim_refresh(self.provider.pk)
            refresh_provider(self.provider.pk, token)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.client_auth_method, 'claude.ai')

    def test_a_failing_check_does_not_break_the_reading(self):
        with patch('scraper.claude_client.current_auth_method', side_effect=RuntimeError('boom')), \
             patch('scraper.claude_client.read_limits', return_value={
                 'five_hour': {'used_percentage': 42, 'resets_at': None}}):
            token = claim_refresh(self.provider.pk)
            refresh_provider(self.provider.pk, token)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.state, 'ok')

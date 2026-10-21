"""The Claude collection can be switched to the server's own client from the admin."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dashboard.models import ProviderStatus


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ClaudeClientModeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('claude-admin', password='test-only-password')
        self.client.force_login(self.user)
        self.url = reverse('scraper_claude_client')
        self.status = ProviderStatus.objects.get(provider='claude')

    def post(self, **payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

    @patch('scraper.claude_client_views.client_available', return_value=True)
    @patch('scraper.claude_client_views.client_session_state', return_value={
        'installed': True, 'connected': True, 'method': 'claude.ai', 'checked_at': None,
        'label': 'Sesión de claude.ai conectada',
        'command': 'docker compose exec worker claude auth login',
        'status_command': 'docker compose exec worker claude auth status'})
    @patch('scraper.claude_client_views.enqueue_refresh')
    def test_enable_switches_the_provider_to_the_server_client(self, enqueue, session, available):
        response = self.post(action='enable')
        self.assertEqual(response.status_code, 200, response.content)
        self.status.refresh_from_db()
        self.assertEqual(self.status.collection_mode, 'client')
        enqueue.assert_called_once_with(self.status.pk)

    @patch('scraper.claude_client_views.client_available', return_value=True)
    @patch('scraper.claude_client_views.client_session_state', return_value={
        'installed': True, 'connected': False, 'method': 'none', 'checked_at': None,
        'label': 'Sin sesión iniciada',
        'command': 'docker compose exec worker claude auth login',
        'status_command': 'docker compose exec worker claude auth status'})
    @patch('scraper.claude_client_views.enqueue_refresh')
    def test_enable_without_a_session_names_the_command_to_run(self, enqueue, session, available):
        """A deployment without keys must be told exactly what to run."""
        response = self.post(action='enable')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body['needs_session'])
        self.assertIn('claude auth login', body['message'])
        self.status.refresh_from_db()
        self.assertEqual(self.status.collection_mode, 'client')

    @patch('scraper.claude_client_views.client_available', return_value=False)
    def test_enable_without_a_client_is_refused(self, available):
        response = self.post(action='enable')
        self.assertEqual(response.status_code, 409)
        self.status.refresh_from_db()
        self.assertNotEqual(self.status.collection_mode, 'client')
        available.assert_called_once()

    @patch('scraper.claude_client_views.enqueue_refresh')
    def test_the_server_is_the_only_recommended_way(self, enqueue):
        """There is no other mode: the server reads the limits."""
        ProviderStatus.objects.filter(pk=self.status.pk).update(collection_mode='client')
        response = self.post(action='disable')
        self.assertEqual(response.status_code, 400, response.content)
        self.status.refresh_from_db()
        self.assertEqual(self.status.collection_mode, 'client')
        enqueue.assert_not_called()

    def test_only_the_superuser_can_switch_the_mode(self):
        self.client.logout()
        staff = get_user_model().objects.create_user('staff', password='test-only-password', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.post(action='enable').status_code, 403)
        self.client.logout()
        self.assertEqual(self.post(action='enable').status_code, 302)

    def test_unknown_action_and_bad_body_are_rejected(self):
        self.assertEqual(self.post(action='whatever').status_code, 400)
        self.assertEqual(self.client.post(self.url, data='not json', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @override_settings(CLAUDE_CLIENT_PATH='/nonexistent/claude')
    def test_a_stale_client_path_does_not_count_as_available(self):
        from scraper.claude_client_views import client_available
        from dashboard.views import can_refresh
        self.assertFalse(client_available())
        ProviderStatus.objects.filter(pk=self.status.pk).update(collection_mode='client')
        self.status.refresh_from_db()
        self.assertFalse(can_refresh(self.status))

    @patch('scraper.claude_client_views.client_session_state', return_value={
        'installed': True, 'connected': False, 'method': 'none', 'checked_at': None,
        'label': 'Sin sesión iniciada',
        'command': 'docker compose exec worker claude auth login',
        'status_command': 'docker compose exec worker claude auth status'})
    def test_the_page_names_the_command_when_the_account_is_not_connected(self, session):
        """A friend who deploys the container without keys must find the command."""
        response = self.client.get(reverse('scraper_connect'))
        self.assertContains(response, 'claude auth login')
        self.assertContains(response, 'Sin sesión iniciada')

    @patch('scraper.claude_client_views.client_session_state', return_value={
        'installed': True, 'connected': True, 'method': 'claude.ai', 'checked_at': None,
        'label': 'Sesión de claude.ai conectada',
        'command': 'docker compose exec worker claude auth login',
        'status_command': 'docker compose exec worker claude auth status'})
    def test_the_page_confirms_a_connected_session(self, session):
        response = self.client.get(reverse('scraper_connect'))
        self.assertContains(response, 'Sesión de claude.ai conectada')
        # The sign-in guide stays available, folded: the session is already there.
        self.assertContains(response, '<details class="claude-guide">')
        self.assertNotContains(response, '<details class="claude-guide" open>')
        self.assertContains(response, 'docker compose exec worker claude auth status')

    def test_the_page_reads_the_state_published_by_the_worker(self):
        """The panel cannot run the client: the session lives in the worker."""
        from django.utils import timezone
        ProviderStatus.objects.filter(provider='claude').update(
            client_auth_method='claude.ai', client_auth_checked_at=timezone.now())
        response = self.client.get(reverse('scraper_connect'))
        self.assertContains(response, 'Sesión de claude.ai conectada')

    def test_the_page_does_not_run_the_client_to_learn_the_session(self):
        """Running the client in the panel service would answer 'no session'."""
        from scraper import claude_client
        ProviderStatus.objects.filter(provider='claude').update(client_auth_method='')
        with patch.object(claude_client, 'auth_state') as auth:
            response = self.client.get(reverse('scraper_connect'))
        auth.assert_not_called()
        self.assertContains(response, 'claude auth login')

    @patch('scraper.claude_client_views.check_claude_session')
    def test_checking_the_session_asks_the_worker(self, check):
        response = self.post(action='check')
        self.assertEqual(response.status_code, 200, response.content)
        check.delay.assert_called_once()

    def test_checking_the_session_without_a_queue_is_reported(self):
        with patch('scraper.claude_client_views.check_claude_session') as check:
            check.delay.side_effect = ConnectionError()
            response = self.post(action='check')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('próxima actualización', response.json()['message'])

    def test_the_page_only_offers_the_current_model(self):
        """The extension, the PC agent and the server browser needed an open browser."""
        body = self.client.get(reverse('scraper_connect')).content.decode()
        for removed in ('Otras opciones', 'Agente del PC', 'Extensión para Chrome/Edge', 'navegador del servidor'):
            self.assertNotIn(removed, body)

    def test_the_guide_lists_every_command_in_order(self):
        """Someone without the context can paste the commands one by one over SSH."""
        from scraper.claude_client import CHECK_COMMAND, LOGIN_COMMAND, STATUS_COMMAND
        ProviderStatus.objects.filter(provider='claude').update(client_auth_method='none')
        body = self.client.get(reverse('scraper_connect')).content.decode()
        positions = [body.index(command) for command in ('cd ~/tokendash', STATUS_COMMAND, LOGIN_COMMAND, CHECK_COMMAND)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<details class="claude-guide" open>', body)
        self.assertIn('docs/VINCULAR_CLAUDE.md', body)

    def test_the_guide_is_folded_once_the_session_is_connected(self):
        ProviderStatus.objects.filter(provider='claude').update(client_auth_method='claude.ai')
        body = self.client.get(reverse('scraper_connect')).content.decode()
        self.assertIn('<details class="claude-guide">', body)

    def test_only_the_server_way_is_offered_for_claude(self):
        """No alternative mode: the server reads the limits."""
        response = self.client.get(reverse('scraper_connect'))
        self.assertNotContains(response, 'Volver al modo anterior')
        self.assertNotContains(response, 'El agente del PC puede consultar los porcentajes')
        self.assertContains(response, 'Que el servidor consulte los límites de Claude')

    def test_the_admin_uses_the_dashboard_colours(self):
        """The admin pages load the dashboard theme."""
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'css/admin-theme')
        page = self.client.get(reverse('scraper_connect'))
        self.assertContains(page, 'css/admin-theme')


class ClaudeEstadoCommandTests(TestCase):
    """«python manage.py claude_estado»: the one command run after the sign-in."""

    def run_command(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('claude_estado', stdout=out)
        return out.getvalue()

    @patch('scraper.tasks.client_readings')
    @patch('scraper.tasks.publish_client_auth_method', return_value='claude.ai')
    @patch('scraper.management.commands.claude_estado.publish_client_auth_method', return_value='claude.ai')
    def test_it_activates_the_mode_and_saves_a_reading(self, published, _, readings):
        from decimal import Decimal
        from scraper.quotas import QuotaReading
        readings.return_value = [QuotaReading('session', 'Sesión de 5 horas', Decimal('4.00'), 'Se reinicia el 21/10 a las 14:19'),
                                 QuotaReading('weekly_all', 'Semana · todos los modelos', Decimal('65.00'), '')]
        ProviderStatus.objects.filter(provider='claude').update(collection_mode='none')
        output = self.run_command()
        status = ProviderStatus.objects.get(provider='claude')
        self.assertEqual(status.collection_mode, 'client')
        self.assertEqual(status.state, ProviderStatus.State.OK)
        self.assertIn('Sesión de 5 horas: 4 % consumido · Se reinicia el 21/10 a las 14:19', output)
        self.assertIn('Semana · todos los modelos: 65 % consumido', output)
        self.assertIn('Cuota de Claude actualizada en el dashboard', output)

    @patch('scraper.management.commands.claude_estado.publish_client_auth_method', return_value='none')
    def test_without_a_session_it_names_the_login_command(self, _):
        from django.core.management.base import CommandError
        from scraper.claude_client import LOGIN_COMMAND
        with self.assertRaisesMessage(CommandError, LOGIN_COMMAND):
            self.run_command()
        # Nothing is activated or read without a session.
        self.assertIsNone(ProviderStatus.objects.get(provider='claude').last_success_at)

    @patch('scraper.tasks.client_readings', side_effect=RuntimeError('raw client output'))
    @patch('scraper.tasks.publish_client_auth_method', return_value='claude.ai')
    @patch('scraper.management.commands.claude_estado.publish_client_auth_method', return_value='claude.ai')
    def test_a_failed_read_is_reported_without_raw_output(self, *_):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError) as raised:
            self.run_command()
        self.assertIn('No se ha podido leer la cuota', str(raised.exception))
        self.assertNotIn('raw client output', str(raised.exception))

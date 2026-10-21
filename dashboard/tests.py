from datetime import timedelta
from io import StringIO
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import IntegrationKey, ProviderStatus, UsageLog
from scraper.models import ProviderCredential

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('operator', password='test-password', is_staff=True)
        self.provider = ProviderStatus.objects.get(provider='chatgpt')
        ProviderStatus.objects.filter(pk=self.provider.pk).update(collection_mode='api')
        self.provider.refresh_from_db()
        self.credential = ProviderCredential.objects.create(provider=self.provider, secret='not-a-real-secret')

    def test_login_required_and_dashboard_renders(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get(reverse('provider-status')).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertContains(response, 'ChatGPT')
        self.assertContains(response, 'Claude')
        self.assertContains(response, 'Actualizar ahora')

    def test_no_data_is_not_zero(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('provider-status'))
        row = next(p for p in response.json()['providers'] if p['provider'] == 'chatgpt')
        self.assertIsNone(row['used_percent'])
        self.assertIsNone(row['available_percent'])
        self.provider.used_percent = Decimal('0')
        self.assertEqual(self.provider.available_percent, 100)

    @patch('dashboard.views.enqueue_refresh', return_value='test-token')
    def test_refresh_is_post_and_staff_only(self, enqueue):
        url = reverse('provider-refresh', args=['chatgpt'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 202)
        enqueue.assert_called_once_with(self.provider.pk)
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_refresh_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('provider-refresh', args=['chatgpt'])).status_code, 403)

    @patch('dashboard.views.enqueue_refresh', side_effect=ConnectionError('private-broker-host'))
    def test_broker_failure_is_sanitized(self, enqueue):
        self.client.force_login(self.user)
        response = self.client.post(reverse('provider-refresh', args=['chatgpt']))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-broker-host', response.content.decode())

    def test_session_and_cooldown(self):
        self.client.force_login(self.user)
        url = reverse('provider-refresh', args=['chatgpt'])
        self.credential.delete()
        self.assertEqual(self.client.post(url).status_code, 409)
        ProviderStatus.objects.filter(pk=self.provider.pk).update(collection_mode='none')
        self.assertEqual(self.client.post(url).status_code, 409)
        ProviderStatus.objects.filter(pk=self.provider.pk).update(collection_mode='api')
        ProviderCredential.objects.create(provider=self.provider, secret='not-a-real-secret')
        self.provider.last_attempt_at = timezone.now()
        self.provider.save()
        self.assertEqual(self.client.post(url).status_code, 429)

    def test_history_separates_quotas_and_missing_days(self):
        self.client.force_login(self.user)
        now = timezone.now()
        for key, value in [('session', 20), ('session', 40), ('weekly', 80)]:
            UsageLog.objects.create(provider=self.provider, quota_key=key, quota_label=key, used_percent=value, observed_at=now)
        UsageLog.objects.create(provider=self.provider, quota_key='old', quota_label='old', used_percent=90, observed_at=now - timedelta(days=45))
        response = self.client.get(reverse('usage-history'))
        data = response.json()
        self.assertEqual(len(data['labels']), 7)
        series = {row['quota']: row['values'] for row in data['series']}
        self.assertEqual(series['session'], [None] * 6 + [30.0])
        self.assertEqual(series['weekly'][-1], 80)
        self.assertNotIn('old', series)
        self.assertEqual(self.client.get(reverse('usage-history') + '?days=abc').status_code, 400)

    def test_every_offered_period_is_accepted(self):
        """7 and 30 days, plus 3 months, 6 months, 1 year and 5 years."""
        self.client.force_login(self.user)
        for days, granularity in [(7, 'day'), (30, 'day'), (90, 'week'), (182, 'week'),
                                  (365, 'month'), (1825, 'year')]:
            response = self.client.get(reverse('usage-history') + f'?days={days}')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['granularity'], granularity)
            self.assertTrue(data['labels'])
            self.assertEqual(data['labels'], sorted(data['labels']))
            # The last label is the first day of the bucket that holds today.
            self.assertLessEqual(data['labels'][-1], timezone.localdate().isoformat())

    def test_a_period_outside_the_offer_is_rejected(self):
        self.client.force_login(self.user)
        for days in (3, 60, 1000, 2000, 0, -7):
            self.assertEqual(self.client.get(reverse('usage-history') + f'?days={days}').status_code, 400)

    def test_long_periods_group_the_readings_without_gaps(self):
        """A year groups by month: two readings in the same month share the bucket."""
        self.client.force_login(self.user)
        now = timezone.now()
        UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                used_percent=20, observed_at=now)
        UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                used_percent=40, observed_at=now - timedelta(days=3))
        data = self.client.get(reverse('usage-history') + '?days=365').json()
        series = {row['quota']: row['values'] for row in data['series']}
        values = [value for value in series['session'] if value is not None]
        self.assertEqual(values, [30.0])  # the mean of the two readings of the month

    def test_five_years_are_grouped_by_year_and_stay_small(self):
        self.client.force_login(self.user)
        now = timezone.now()
        UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                used_percent=20, observed_at=now)
        UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                used_percent=40, observed_at=now - timedelta(days=400))
        data = self.client.get(reverse('usage-history') + '?days=1825').json()
        self.assertEqual(data['granularity'], 'year')
        # One point per year, not one per day.
        self.assertLessEqual(len(data['labels']), 7)
        series = {row['quota']: row['values'] for row in data['series']}
        self.assertEqual(len(series['session']), len(data['labels']))
        self.assertEqual(sum(value is not None for value in series['session']), 2)


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class HomeAssistantTests(TestCase):
    def setUp(self):
        record = IntegrationKey(name='Casa')
        self.key = record.generate()
        record.save()
        self.record = record
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {self.key}'}
        self.claude = ProviderStatus.objects.get(provider='claude')
        now = timezone.now()
        ProviderStatus.objects.filter(pk=self.claude.pk).update(
            state='ok', used_percent=26, last_success_at=now, quotas=[
                {'key': 'session', 'label': 'Sesión de 5 horas', 'used_percent': '26.00', 'resets_at': (now + timedelta(hours=2)).isoformat()},
                {'key': 'weekly_all', 'label': 'Semana', 'used_percent': '40.50', 'resets_at': (now - timedelta(hours=1)).isoformat()},
            ])

    def test_only_the_hash_is_stored(self):
        self.assertNotIn(self.key, self.record.key_hash)
        self.assertTrue(self.key.startswith(self.record.prefix))

    def test_each_module_has_its_own_page_that_can_be_framed(self):
        for module, text in [('chatgpt', 'ChatGPT'), ('claude', 'Claude'), ('grafica', 'Evolución de los límites')]:
            response = self.client.get(reverse('embed', args=[module]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, text)
            self.assertNotIn('X-Frame-Options', response.headers)
        # One module per page: the ChatGPT page has neither Claude nor the chart.
        response = self.client.get(reverse('embed', args=['chatgpt']))
        self.assertNotContains(response, 'data-provider="claude"')
        self.assertNotContains(response, 'id="history"')
        self.assertNotContains(response, 'Actualizar ahora')
        self.assertEqual(self.client.get(reverse('embed', args=['otro'])).status_code, 404)

    def test_the_rest_of_the_site_still_refuses_frames(self):
        self.assertEqual(self.client.get(reverse('login')).headers['X-Frame-Options'], 'DENY')

    def test_the_api_accepts_the_key_and_rejects_a_wrong_one(self):
        self.assertEqual(self.client.get(reverse('provider-status'), **self.auth).status_code, 200)
        self.assertEqual(self.client.get(reverse('usage-history'), **self.auth).status_code, 200)
        wrong = self.client.get(reverse('provider-status'), HTTP_AUTHORIZATION='Bearer td_otra')
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.client.get(reverse('provider-status')).status_code, 302)
        self.record.refresh_from_db()
        self.assertIsNotNone(self.record.last_used_at)

    def test_a_deleted_key_stops_working(self):
        self.record.delete()
        self.assertEqual(self.client.get(reverse('ha-sensor', args=['claude']), **self.auth).status_code, 401)

    def test_the_key_cannot_refresh(self):
        self.assertEqual(self.client.post(reverse('provider-refresh', args=['claude']), **self.auth).status_code, 302)

    def test_sensor_flattens_the_windows(self):
        data = self.client.get(reverse('ha-sensor', args=['claude']), **self.auth).json()
        self.assertEqual(data['state'], 'ok')
        self.assertEqual(data['session_used_percent'], 26.0)
        self.assertFalse(data['session_window_reset'])
        self.assertEqual(data['weekly_used_percent'], 40.5)
        self.assertTrue(data['weekly_window_reset'])
        self.assertEqual(self.client.get(reverse('ha-sensor', args=['otro']), **self.auth).status_code, 404)

    def test_no_data_is_null_not_zero(self):
        data = self.client.get(reverse('ha-sensor', args=['chatgpt']), **self.auth).json()
        self.assertIsNone(data['used_percent'])
        self.assertIsNone(data['session_used_percent'])
        self.assertIsNone(data['weekly_used_percent'])

    def test_admin_shows_the_key_once(self):
        admin = get_user_model().objects.create_superuser('admin', password='test-password')
        self.client.force_login(admin)
        response = self.client.post(reverse('admin:dashboard_integrationkey_add'), {'name': 'Salón'})
        self.assertEqual(response.status_code, 200)
        created = IntegrationKey.objects.get(name='Salón')
        key = response.context['key']
        self.assertEqual(IntegrationKey.digest(key), created.key_hash)
        self.assertContains(response, f'/ha/grafica/#clave={key}')
        self.assertIn('no-store', response.headers['Cache-Control'])
        page = self.client.get(reverse('admin:dashboard_integrationkey_change', args=[created.pk]))
        self.assertNotContains(page, key)

    def test_admin_has_no_groups_nor_periodic_tasks(self):
        admin = get_user_model().objects.create_superuser('admin', password='test-password')
        self.client.force_login(admin)
        page = self.client.get(reverse('admin:index'))
        self.assertContains(page, 'Usuarios')
        self.assertNotContains(page, 'Grupos')
        self.assertNotContains(page, 'Tareas periódicas')


class FirstSignInTests(TestCase):
    """A new installation starts with admin / tokendash and forces a new password."""

    def setUp(self):
        call_command('crear_admin_inicial', stdout=StringIO())

    def test_default_admin_only_on_empty_installation(self):
        admin = get_user_model().objects.get()
        self.assertEqual(admin.username, 'admin')
        self.assertTrue(admin.is_superuser and admin.is_staff)
        call_command('crear_admin_inicial', stdout=StringIO())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_default_password_is_forced_to_change(self):
        self.client.post(reverse('login'), {'username': 'admin', 'password': 'tokendash'})
        for url in ('/', '/admin/', reverse('scraper_connect')):
            self.assertRedirects(self.client.get(url), reverse('password_change'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/api/status/').status_code, 403)
        page = self.client.get(reverse('password_change'))
        self.assertContains(page, 'PRIMER ACCESO')
        rejected = self.client.post(reverse('password_change'), {
            'old_password': 'tokendash', 'new_password1': 'tokendash', 'new_password2': 'tokendash'})
        self.assertContains(rejected, 'contraseña inicial')
        done = self.client.post(reverse('password_change'), {
            'old_password': 'tokendash', 'new_password1': 'Otra-clave-larga-9', 'new_password2': 'Otra-clave-larga-9'})
        self.assertRedirects(done, reverse('password_change_done'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertTrue(get_user_model().objects.get().check_password('Otra-clave-larga-9'))

    def test_admin_login_with_default_password_is_also_forced(self):
        self.client.post(reverse('admin:login'), {'username': 'admin', 'password': 'tokendash'})
        self.assertRedirects(self.client.get('/admin/'), reverse('password_change'), fetch_redirect_response=False)

    def test_other_passwords_are_not_forced(self):
        admin = get_user_model().objects.get()
        admin.set_password('Otra-clave-larga-9'); admin.save()
        self.client.post(reverse('login'), {'username': 'admin', 'password': 'Otra-clave-larga-9'})
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertContains(self.client.get(reverse('password_change')), 'TU CUENTA')

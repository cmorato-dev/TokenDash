from datetime import timedelta
from io import StringIO
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from .models import IntegrationKey, ProviderStatus, RefreshSettings, UsageLog
from scraper.models import ProviderCredential
from scraper.quotas import QuotaUnavailable

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('operator', password='test-password', is_staff=True)
        self.provider = ProviderStatus.objects.get(provider='chatgpt')
        ProviderStatus.objects.filter(pk=self.provider.pk).update(collection_mode='api')
        self.provider.refresh_from_db()
        self.credential = ProviderCredential.objects.create(provider=self.provider, secret='not-a-real-secret')

    def test_login_required_and_dashboard_renders(self):
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        self.assertEqual(self.client.get(reverse('provider-status')).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'ChatGPT')
        self.assertContains(response, 'Claude')
        self.assertContains(response, 'Refresh now')

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
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json())

    def test_refresh_csrf(self):
        # The dashboard reads errors with fetch(): they must be JSON, not Django's HTML page.
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse('provider-refresh', args=['chatgpt']))
        self.assertEqual(response.status_code, 403)
        self.assertIn('Reload it', response.json()['error'])
        self.assertEqual(client.post(reverse('login')).headers['Content-Type'], 'text/html; charset=utf-8')

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

    def test_history_preserves_intraday_peaks_resets_and_separate_quotas(self):
        self.client.force_login(self.user)
        now = timezone.now()
        for hours, value in [(6, 8), (5, 100), (4, 0), (1, 87)]:
            UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                    used_percent=value, observed_at=now - timedelta(hours=hours))
        UsageLog.objects.create(provider=self.provider, quota_key='weekly', quota_label='weekly',
                                used_percent=97, observed_at=now - timedelta(minutes=30))
        for offset in [-45, 1]:
            UsageLog.objects.create(provider=self.provider, quota_key='outside', quota_label='outside',
                                    used_percent=90, observed_at=now + timedelta(days=offset))
        for days in (1, 7, 30):
            data = self.client.get(reverse('usage-history') + f'?days={days}').json()
            series = {row['quota']: row['points'] for row in data['series']}
            self.assertEqual([p['used'] for p in series['session']], [8, 100, 0, 87])
            self.assertEqual([p['used'] for p in series['weekly']], [97])
            self.assertNotIn('outside', series)
            self.assertEqual(series['session'][0]['at'], (now - timedelta(hours=6)).isoformat())
        self.assertEqual(self.client.get(reverse('usage-history') + '?days=abc').status_code, 400)

    @patch('dashboard.views.timezone.now')
    def test_24_hours_uses_a_rolling_window_and_never_fills_missing_readings(self, clock):
        from datetime import datetime, timezone as dt_timezone
        now = datetime(2026, 11, 6, 18, tzinfo=dt_timezone.utc)
        clock.return_value = now
        self.client.force_login(self.user)
        for hours, value in [(25, 100), (23, 87)]:
            UsageLog.objects.create(provider=self.provider, quota_key='session', quota_label='session',
                                    used_percent=value, observed_at=now - timedelta(hours=hours))
        data = self.client.get(reverse('usage-history') + '?days=1').json()
        self.assertEqual(data['start_at'], (now - timedelta(hours=24)).isoformat())
        self.assertEqual(data['end_at'], now.isoformat())
        self.assertEqual([p['used'] for p in data['series'][0]['points']], [87])

    @override_settings(TIME_ZONE='Europe/Madrid')
    @patch('dashboard.views.timezone.now')
    def test_history_day_boundaries_follow_daylight_saving_time(self, clock):
        from datetime import datetime, timezone as dt_timezone
        clock.return_value = datetime(2026, 10, 26, 12, tzinfo=dt_timezone.utc)
        self.client.force_login(self.user)
        data = self.client.get(reverse('usage-history')).json()
        self.assertIn('2026-10-25T00:00:00+02:00', data['day_boundaries'])
        self.assertIn('2026-10-26T00:00:00+01:00', data['day_boundaries'])
        self.assertEqual(data['series'], [])

    def test_every_offered_period_is_accepted(self):
        self.client.force_login(self.user)
        for days, granularity in [(1, 'observation'), (7, 'observation'), (30, 'observation'),
                                  (90, 'week'), (182, 'week'), (365, 'month'), (1825, 'year')]:
            response = self.client.get(reverse('usage-history') + f'?days={days}')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['granularity'], granularity)
            if granularity == 'observation':
                self.assertTrue(data['day_boundaries'])
            else:
                self.assertTrue(data['labels'])
                self.assertEqual(data['labels'], sorted(data['labels']))

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
        for module, text in [('chatgpt', 'ChatGPT'), ('claude', 'Claude'), ('chart', 'Limits over time'), ('grafica', 'Limits over time')]:
            response = self.client.get(reverse('embed', args=[module]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, text)
            self.assertNotIn('X-Frame-Options', response.headers)
        # One module per page: the ChatGPT page has neither Claude nor the chart.
        response = self.client.get(reverse('embed', args=['chatgpt']))
        self.assertNotContains(response, 'data-provider="claude"')
        self.assertNotContains(response, 'id="history"')
        self.assertNotContains(response, 'Refresh now')
        self.assertEqual(self.client.get(reverse('embed', args=['otro'])).status_code, 404)

    def test_modules_created_before_the_language_prefix_still_work(self):
        # Home Assistant cards made with /ha/grafica/#clave=… keep their address.
        self.addCleanup(translation.activate, 'en')  # a Spanish request leaves Spanish active
        response = self.client.get('/ha/grafica/', HTTP_ACCEPT_LANGUAGE='es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Evolución de los límites')
        self.assertNotIn('X-Frame-Options', response.headers)

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
        self.assertContains(response, f'/en/ha/chart/#key={key}')
        self.assertIn('no-store', response.headers['Cache-Control'])
        page = self.client.get(reverse('admin:dashboard_integrationkey_change', args=[created.pk]))
        self.assertNotContains(page, key)

    def test_admin_has_no_groups_nor_periodic_tasks(self):
        admin = get_user_model().objects.create_superuser('admin', password='test-password')
        self.client.force_login(admin)
        page = self.client.get(reverse('admin:index'))
        self.assertContains(page, 'Users')
        self.assertNotContains(page, 'Groups')
        self.assertNotContains(page, 'Periodic tasks')


class FirstSignInTests(TestCase):
    """A new installation starts with admin / tokendash and forces a new password."""

    def setUp(self):
        call_command('create_initial_admin', stdout=StringIO())

    def test_default_admin_only_on_empty_installation(self):
        admin = get_user_model().objects.get()
        self.assertEqual(admin.username, 'admin')
        self.assertTrue(admin.is_superuser and admin.is_staff)
        call_command('create_initial_admin', stdout=StringIO())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_default_password_is_forced_to_change(self):
        self.client.post(reverse('login'), {'username': 'admin', 'password': 'tokendash'})
        for url in (reverse('dashboard'), reverse('admin:index'), reverse('scraper_connect')):
            self.assertRedirects(self.client.get(url), reverse('password_change'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/api/status/').status_code, 403)
        page = self.client.get(reverse('password_change'))
        self.assertContains(page, 'FIRST SIGN-IN')
        rejected = self.client.post(reverse('password_change'), {
            'old_password': 'tokendash', 'new_password1': 'tokendash', 'new_password2': 'tokendash'})
        self.assertContains(rejected, 'initial TokenDash password')
        done = self.client.post(reverse('password_change'), {
            'old_password': 'tokendash', 'new_password1': 'Otra-clave-larga-9', 'new_password2': 'Otra-clave-larga-9'})
        self.assertRedirects(done, reverse('password_change_done'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertTrue(get_user_model().objects.get().check_password('Otra-clave-larga-9'))

    def test_admin_login_with_default_password_is_also_forced(self):
        self.client.post(reverse('admin:login'), {'username': 'admin', 'password': 'tokendash'})
        self.assertRedirects(self.client.get(reverse('admin:index')), reverse('password_change'), fetch_redirect_response=False)

    def test_other_passwords_are_not_forced(self):
        admin = get_user_model().objects.get()
        admin.set_password('Otra-clave-larga-9'); admin.save()
        self.client.post(reverse('login'), {'username': 'admin', 'password': 'Otra-clave-larga-9'})
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertContains(self.client.get(reverse('password_change')), 'YOUR ACCOUNT')


class RefreshSettingsTests(TestCase):
    """The refresh interval is chosen in the admin; beat only ticks every minute."""

    def tick(self, at):
        from scraper.tasks import refresh_if_due
        with patch('scraper.tasks.timezone.now', return_value=at), patch('scraper.tasks.refresh_all') as refresh:
            refresh_if_due()
        return refresh.called

    def test_interval_from_the_admin_is_respected(self):
        start = timezone.now()
        self.assertTrue(self.tick(start))  # the first tick reads at once
        self.assertFalse(self.tick(start + timedelta(minutes=10)))
        self.assertTrue(self.tick(start + timedelta(minutes=20)))
        RefreshSettings.objects.update(refresh_minutes=60)
        self.assertFalse(self.tick(start + timedelta(minutes=50)))
        self.assertTrue(self.tick(start + timedelta(minutes=80)))

    @override_settings(SCRAPE_INTERVAL_MINUTES=30)
    def test_first_value_comes_from_the_env(self):
        self.assertEqual(RefreshSettings.load().refresh_minutes, 30)

    def test_admin_has_a_single_settings_page(self):
        admin = get_user_model().objects.create_superuser('jefe', '', 'Otra-clave-larga-9')
        self.client.force_login(admin)
        listing = self.client.get(reverse('admin:dashboard_refreshsettings_changelist'))
        change_url = reverse('admin:dashboard_refreshsettings_change', args=[RefreshSettings.load().pk])
        self.assertRedirects(listing, change_url)
        self.assertContains(self.client.get(change_url), 'Every 2 hours')
        self.client.post(change_url, {'accounts': 'both', 'refresh_minutes': 120})
        self.assertEqual(RefreshSettings.load().refresh_minutes, 120)
        self.assertEqual(self.client.post(change_url, {'accounts': 'both', 'refresh_minutes': 5}).status_code, 200)  # not offered
        self.assertEqual(RefreshSettings.load().refresh_minutes, 120)
        self.assertNotContains(self.client.get(change_url), 'deletelink')
        self.assertEqual(self.client.get(reverse('admin:dashboard_refreshsettings_add')).status_code, 403)
        self.assertContains(self.client.get(reverse('scraper_connect')), 'every 120 minutes')


class SingleAccountTests(TestCase):
    """Someone who pays for one subscription sees, and reads, only that account."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser('jefe', '', 'Otra-clave-larga-9')
        self.client.force_login(self.user)
        ProviderStatus.objects.update(collection_mode='client')
        for status in ProviderStatus.objects.all():
            UsageLog.objects.create(provider=status, quota_key='session', quota_label='5 horas',
                                    used_percent=30, observed_at=timezone.now())

    def choose(self, accounts):
        change_url = reverse('admin:dashboard_refreshsettings_change', args=[RefreshSettings.load().pk])
        self.client.post(change_url, {'accounts': accounts, 'refresh_minutes': 20})
        self.assertEqual(RefreshSettings.load().accounts, accounts)

    def test_both_accounts_by_default(self):
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'data-provider="chatgpt"')
        self.assertContains(page, 'data-provider="claude"')
        self.assertNotContains(page, 'provider-card wide')

    @patch('scraper.tasks.enqueue_refresh')
    def test_only_claude(self, enqueue):
        self.choose('claude')
        page = self.client.get(reverse('dashboard'))
        self.assertNotContains(page, 'data-provider="chatgpt"')
        self.assertContains(page, 'provider-card wide')
        self.assertContains(page, 'your Claude account')
        self.assertEqual([p['provider'] for p in self.client.get(reverse('provider-status')).json()['providers']], ['claude'])
        self.assertEqual({s['provider'] for s in self.client.get(reverse('usage-history')).json()['series']}, {'claude'})
        self.assertEqual(self.client.post(reverse('provider-refresh', args=['chatgpt'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('ha-sensor', args=['chatgpt'])).status_code, 404)
        connect = self.client.get(reverse('scraper_connect'))
        self.assertNotContains(connect, 'id="codex-card"')
        self.assertContains(connect, 'You only use Claude')
        from scraper.tasks import refresh_all
        refresh_all()
        enqueue.assert_called_once_with(ProviderStatus.objects.get(provider='claude').pk)

    def test_only_chatgpt(self):
        self.choose('chatgpt')
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'data-provider="chatgpt"')
        self.assertNotContains(page, 'data-provider="claude"')
        self.assertNotContains(self.client.get(reverse('scraper_connect')), 'id="claude-card"')


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class LanguageTests(TestCase):
    """Every page exists in English (/en/) and Spanish (/es/); the API answers in the language asked for."""

    def setUp(self):
        # A request leaves its language active in the thread: start the next test in English.
        self.addCleanup(translation.activate, 'en')
        self.user = get_user_model().objects.create_superuser('jefe', '', 'Otra-clave-larga-9')
        self.claude = ProviderStatus.objects.get(provider='claude')
        ProviderStatus.objects.filter(pk=self.claude.pk).update(
            state='unavailable', used_percent=26, last_success_at=timezone.now(),
            last_error=QuotaUnavailable.message, quotas=[
                {'key': 'session', 'label': '5-hour session', 'used_percent': '26.00',
                 'resets_at': '2030-01-02T06:41:00+00:00'},
                {'key': 'weekly', 'label': 'Codex · 3 h window', 'used_percent': '10.00'}])

    def test_an_address_without_a_language_follows_the_browser(self):
        self.assertRedirects(self.client.get('/', HTTP_ACCEPT_LANGUAGE='es-ES,es;q=0.9'), '/es/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/', HTTP_ACCEPT_LANGUAGE='en-GB'), '/en/', fetch_redirect_response=False)
        # A language TokenDash does not have falls back to English.
        self.assertRedirects(self.client.get('/', HTTP_ACCEPT_LANGUAGE='de'), '/en/', fetch_redirect_response=False)

    def test_each_page_is_written_in_its_language(self):
        self.client.force_login(self.user)
        spanish = self.client.get('/es/')
        self.assertContains(spanish, '<html lang="es">')
        self.assertContains(spanish, 'Actualizar ahora')
        self.assertContains(spanish, 'src="/es/jsi18n/"')
        english = self.client.get('/en/')
        self.assertContains(english, '<html lang="en">')
        self.assertContains(english, 'Refresh now')
        # Search engines learn about the other version and the address without a prefix.
        for page in (spanish, english):
            self.assertContains(page, 'hreflang="en" href="http://testserver/en/"')
            self.assertContains(page, 'hreflang="es" href="http://testserver/es/"')
            self.assertContains(page, 'hreflang="x-default" href="http://testserver/"')
        login = self.client.get('/es/accounts/login/')
        self.assertContains(login, 'hreflang="en" href="http://testserver/en/accounts/login/"')
        self.assertContains(self.client.get('/es/admin/'), 'Conectar cuentas')

    def test_the_switch_keeps_the_page_and_remembers_the_choice(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('set_language'), {'language': 'es', 'next': '/en/admin/connect/'})
        self.assertRedirects(response, '/es/admin/connect/', fetch_redirect_response=False)
        # The API has no prefix: it follows the remembered choice.
        data = self.client.get(reverse('provider-status')).json()
        self.assertEqual(next(p for p in data['providers'] if p['provider'] == 'claude')['state_label'],
                         'No se ha podido leer una cuota de esta cuenta')

    def test_the_api_answers_in_the_language_asked_for(self):
        self.client.force_login(self.user)
        for language, label, reset, error, codex in (
                ('en', '5-hour session', 'Resets on Jan 2 at 07:41', 'No recognisable quota', 'Codex · 3 h window'),
                ('es', 'Sesión de 5 horas', 'Se reinicia el 2/1 a las 07:41', 'No hemos encontrado', 'Codex · ventana de 3 h')):
            data = self.client.get(reverse('provider-status'), HTTP_ACCEPT_LANGUAGE=language).json()
            claude = next(p for p in data['providers'] if p['provider'] == 'claude')
            self.assertEqual(claude['quota_label'], label)
            self.assertEqual(claude['quotas'][0]['reset_text'], reset)
            self.assertEqual(claude['quotas'][1]['label'], codex)
            self.assertIn(error, claude['last_error'])
        missing = self.client.post(reverse('provider-refresh', args=['otro']), HTTP_ACCEPT_LANGUAGE='es')
        self.assertEqual(missing.json()['error'], 'Proveedor desconocido.')

    def test_the_script_texts_come_in_each_language(self):
        self.assertContains(self.client.get('/es/jsi18n/'), 'Llevas un')
        self.assertNotContains(self.client.get('/en/jsi18n/'), 'Llevas un')

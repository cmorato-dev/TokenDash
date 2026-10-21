from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ConnectionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='test-only-password')
        self.client.force_login(self.admin)

    def test_guided_page_and_entry_link(self):
        self.assertContains(self.client.get(reverse('admin:index')), 'Conectar cuentas')
        response = self.client.get(reverse('scraper_connect'))
        self.assertContains(response, 'Iniciar sesión con ChatGPT')
        self.assertContains(response, 'Guía paso a paso para vincular Claude')
        # The options that needed an open browser are no longer offered.
        self.assertNotContains(response, 'Otras opciones')
        self.assertNotContains(response, 'Guardar y activar')
        self.assertNotContains(response, 'connections.js')
        self.assertIn('no-store', response['Cache-Control'])

    def test_the_admin_pages_use_the_dashboard_theme(self):
        """Every admin page loads the same stylesheet as the dashboard."""
        for url in (reverse('admin:index'), reverse('scraper_connect')):
            self.assertContains(self.client.get(url), 'css/admin-theme')

    def test_superuser_required(self):
        operator = get_user_model().objects.create_user('staff', is_staff=True)
        self.client.force_login(operator)
        self.assertEqual(self.client.get(reverse('scraper_connect')).status_code, 403)

    def test_the_old_address_still_leads_to_the_page(self):
        response = self.client.get('/admin/scraper/scrapersession/connect/')
        self.assertRedirects(response, reverse('scraper_connect'), status_code=301)

    def test_retired_endpoints_are_gone(self):
        for url in ('/api/browser-sync/', '/api/agent/ingest/', '/api/tokens/'):
            self.assertEqual(self.client.post(url).status_code, 404, url)

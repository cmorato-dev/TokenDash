from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ConnectionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='test-only-password')
        self.client.force_login(self.admin)

    def test_guided_page_and_entry_link(self):
        self.assertContains(self.client.get(reverse('admin:index')), 'Connect accounts')
        response = self.client.get(reverse('scraper_connect'))
        self.assertContains(response, 'Sign in with ChatGPT')
        self.assertContains(response, 'Step-by-step guide to link Claude')
        # The options that needed an open browser are no longer offered.
        self.assertNotContains(response, 'Other options')
        self.assertNotContains(response, 'Save and turn on')
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
        for old in ('/en/admin/scraper/scrapersession/connect/', '/en/admin/conectar/'):
            self.assertRedirects(self.client.get(old), reverse('scraper_connect'), status_code=301)
        # Without the language prefix it goes through the visitor's language first.
        self.addCleanup(translation.activate, 'en')
        response = self.client.get('/admin/conectar/', follow=True, HTTP_ACCEPT_LANGUAGE='es')
        self.assertEqual(response.redirect_chain[-1][0], '/es/admin/connect/')

    def test_retired_endpoints_are_gone(self):
        for url in ('/api/browser-sync/', '/api/agent/ingest/', '/api/tokens/'):
            self.assertEqual(self.client.post(url).status_code, 404, url)

"""A failure must show the reason that was given, not only the generic text."""
from django.test import SimpleTestCase

from scraper.quotas import QuotaUnavailable, ScrapeFailure, SessionExpired


class ScrapeFailureMessageTests(SimpleTestCase):
    def test_a_specific_reason_replaces_the_generic_one(self):
        failure = ScrapeFailure('La cuenta no está conectada con una suscripción.')
        self.assertEqual(failure.message, 'La cuenta no está conectada con una suscripción.')
        self.assertEqual(str(failure), 'La cuenta no está conectada con una suscripción.')

    def test_without_a_reason_the_class_text_is_kept(self):
        failure = ScrapeFailure()
        self.assertEqual(failure.message, ScrapeFailure.message)
        self.assertEqual(failure.state, 'error')

    def test_a_subclass_keeps_its_own_state_and_text(self):
        failure = SessionExpired('La sesión del servidor caducó.')
        self.assertEqual(failure.state, 'expired')
        self.assertEqual(failure.message, 'La sesión del servidor caducó.')
        self.assertEqual(str(failure), 'La sesión del servidor caducó.')

    def test_a_subclass_without_a_reason_keeps_its_class_text(self):
        failure = QuotaUnavailable()
        self.assertEqual(failure.message, QuotaUnavailable.message)
        self.assertEqual(failure.state, 'unavailable')

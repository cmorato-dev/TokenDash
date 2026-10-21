"""A failure must show the reason that was given, not only the generic text."""
from django.test import SimpleTestCase

from scraper.quotas import QuotaUnavailable, ScrapeFailure, SessionExpired


class ScrapeFailureMessageTests(SimpleTestCase):
    def test_a_specific_reason_replaces_the_generic_one(self):
        failure = ScrapeFailure('The account is not connected to a subscription.')
        self.assertEqual(failure.message, 'The account is not connected to a subscription.')
        self.assertEqual(str(failure), 'The account is not connected to a subscription.')

    def test_without_a_reason_the_class_text_is_kept(self):
        failure = ScrapeFailure()
        self.assertEqual(failure.message, ScrapeFailure.message)
        self.assertEqual(failure.state, 'error')

    def test_a_subclass_keeps_its_own_state_and_text(self):
        failure = SessionExpired('The server session expired.')
        self.assertEqual(failure.state, 'expired')
        self.assertEqual(failure.message, 'The server session expired.')
        self.assertEqual(str(failure), 'The server session expired.')

    def test_a_subclass_without_a_reason_keeps_its_class_text(self):
        failure = QuotaUnavailable()
        self.assertEqual(failure.message, QuotaUnavailable.message)
        self.assertEqual(failure.state, 'unavailable')

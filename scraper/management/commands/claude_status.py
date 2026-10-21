from django.core.management.base import BaseCommand, CommandError
from django.utils import formats, timezone
from django.utils.translation import gettext as _

from dashboard.models import ProviderStatus
from scraper.quotas import display_quota
from scraper.claude_client import LOGIN_COMMAND, describe_session
from scraper.tasks import claim_refresh, publish_client_auth_method, refresh_provider


class Command(BaseCommand):
    help = ("Checks the server's Claude session, turns on reading the quota and refreshes it now. "
            'Runs in the worker: docker compose exec worker python manage.py claude_status')

    def handle(self, **options):
        # Only the kind of credential is published and printed, never the credential,
        # the e-mail or the organization.
        method = publish_client_auth_method()
        label, connected = describe_session(method)
        self.stdout.write(_('Claude session on the server: %(label)s') % {'label': label})
        if not connected:
            raise CommandError(_('Sign in with: %(command)s') % {'command': LOGIN_COMMAND})

        status = ProviderStatus.objects.get(provider='claude')
        if status.collection_mode != 'client':
            ProviderStatus.objects.filter(pk=status.pk).update(
                collection_mode='client', refresh_token='', refresh_expires_at=None, last_error='')
            self.stdout.write(_('Reading the quota on the server: on.'))
        token = claim_refresh(status.pk)
        if token is None:
            self.stdout.write(_('A refresh is already running: wait a minute and run the command again.'))
            return
        # Runs here, in the worker that holds the session, instead of through the queue.
        refresh_provider(status.pk, token)
        status.refresh_from_db()
        if status.state != ProviderStatus.State.OK:
            reason = _(status.last_error) if status.last_error else status.get_state_display()
            raise CommandError(_('The quota could not be read: %(reason)s') % {'reason': reason})
        for quota in map(display_quota, status.quotas):
            line = '  ' + _('%(label)s: %(percent)s %% used') % {
                'label': quota['label'], 'percent': quota['used_percent'].rstrip('0').rstrip('.')}
            if quota['reset_text']:
                line += f' · {quota["reset_text"]}'
            self.stdout.write(line)
        when = formats.date_format(timezone.localtime(status.last_success_at), 'j/n H:i')
        self.stdout.write(self.style.SUCCESS(_('Claude quota updated on the dashboard (%(when)s).') % {'when': when}))

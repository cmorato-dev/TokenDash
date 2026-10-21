from django.core.management.base import BaseCommand, CommandError
from django.utils import formats, timezone

from dashboard.models import ProviderStatus
from scraper.claude_client import LOGIN_COMMAND, describe_session
from scraper.tasks import claim_refresh, publish_client_auth_method, refresh_provider


class Command(BaseCommand):
    help = ('Comprueba la sesión de Claude del servidor, activa la lectura de la cuota y la '
            'actualiza ahora. Se ejecuta en el worker: docker compose exec worker python manage.py claude_estado')

    def handle(self, **options):
        # Only the kind of credential is published and printed, never the credential,
        # the e-mail or the organization.
        method = publish_client_auth_method()
        label, connected = describe_session(method)
        self.stdout.write(f'Sesión de Claude en el servidor: {label}')
        if not connected:
            raise CommandError(f'Inicia la sesión con: {LOGIN_COMMAND}')

        status = ProviderStatus.objects.get(provider='claude')
        if status.collection_mode != 'client':
            ProviderStatus.objects.filter(pk=status.pk).update(
                collection_mode='client', refresh_token='', refresh_expires_at=None, last_error='')
            self.stdout.write('Lectura de la cuota en el servidor: activada.')
        token = claim_refresh(status.pk)
        if token is None:
            self.stdout.write('Ya hay una actualización en curso: espera un minuto y repite el comando.')
            return
        # Runs here, in the worker that holds the session, instead of through the queue.
        refresh_provider(status.pk, token)
        status.refresh_from_db()
        if status.state != ProviderStatus.State.OK:
            raise CommandError(f'No se ha podido leer la cuota: {status.last_error or status.get_state_display()}')
        for quota in status.quotas:
            line = f'  {quota["label"]}: {quota["used_percent"].rstrip("0").rstrip(".")} % consumido'
            if quota.get('reset_text'):
                line += f' · {quota["reset_text"]}'
            self.stdout.write(line)
        when = formats.date_format(timezone.localtime(status.last_success_at), 'j/n H:i')
        self.stdout.write(self.style.SUCCESS(f'Cuota de Claude actualizada en el dashboard ({when}).'))

import logging
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from dashboard.models import ProviderStatus, RefreshSettings, UsageLog
from .models import ProviderCredential
from .quotas import QuotaUnavailable, ScrapeFailure

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300


def client_readings():
    """Subscription limits read by the official Claude Code client on this server."""
    from .claude_client import epoch, read_limits
    from .quotas import claude_readings
    windows = read_limits()
    return claude_readings([
        {'name': name, 'used_percentage': window['used_percentage'],
         'resets_at': epoch(window.get('resets_at'))}
        for name, window in windows.items()
    ])


def publish_client_auth_method():
    """Publish how the client is signed in, for the admin panel.

    The client's session lives in a private volume of this container, so the
    panel (another service) cannot ask the client: it reads this record
    instead. Only the kind of credential is published, never the credential.
    """
    from .claude_client import current_auth_method
    method = current_auth_method()
    ProviderStatus.objects.filter(provider='claude').update(
        client_auth_method=method, client_auth_checked_at=timezone.now())
    return method


@shared_task
def check_claude_session():
    """Ask the official client how it is signed in, and publish the answer.

    Runs on the worker, which is the container that holds the client's
    session. Useful on a deployment without keys: the panel can then say
    whether the account is connected yet.
    """
    try:
        return publish_client_auth_method()
    except Exception:
        logger.warning('No se ha podido comprobar la sesión de Claude en el servidor.')
        return None

def claim_refresh(provider_id):
    now = timezone.now()
    token = str(uuid4())
    claimed = ProviderStatus.objects.filter(pk=provider_id, collection_mode__in=('api', 'client')).filter(
        Q(refresh_expires_at__isnull=True) | Q(refresh_expires_at__lte=now)
    ).update(refresh_token=token, refresh_expires_at=now + timedelta(seconds=LEASE_SECONDS))
    return token if claimed else None

def enqueue_refresh(provider_id):
    token = claim_refresh(provider_id)
    if token:
        try:
            refresh_provider.apply_async(args=[provider_id, token], expires=240)
        except Exception:
            ProviderStatus.objects.filter(pk=provider_id, refresh_token=token).update(
                refresh_token='', refresh_expires_at=None,
            )
            raise
    return token

@shared_task
def refresh_all():
    # Only the accounts chosen in the settings: a hidden account is never read.
    shown = RefreshSettings.shown_providers()
    for provider_id in ProviderCredential.objects.filter(provider__collection_mode='api', provider__provider__in=shown).values_list('provider_id', flat=True):
        enqueue_refresh(provider_id)
    # The official Claude Code client can read the subscription limits on the server itself.
    for provider_id in ProviderStatus.objects.filter(collection_mode='client', provider__in=shown).values_list('pk', flat=True):
        enqueue_refresh(provider_id)


@shared_task
def refresh_if_due():
    """Beat calls this every minute; it refreshes when the interval chosen in the admin has passed."""
    current = RefreshSettings.load()
    now = timezone.now()
    # 30 s of margin so a tick that arrives a little early does not wait a whole extra minute.
    if current.last_scheduled_at and now - current.last_scheduled_at < timedelta(minutes=current.refresh_minutes, seconds=-30):
        return False
    # Claim the run, so two overlapping ticks cannot start it twice.
    if not RefreshSettings.objects.filter(pk=current.pk, last_scheduled_at=current.last_scheduled_at).update(last_scheduled_at=now):
        return False
    refresh_all()
    return True


@shared_task
def refresh_provider(provider_id, token):
    now = timezone.now()
    valid = ProviderStatus.objects.filter(pk=provider_id, refresh_token=token, refresh_expires_at__gt=now)
    # Claim execution exactly once even if a broker delivers the same message twice.
    if not valid.filter(Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lt=F('refresh_expires_at') - timedelta(seconds=LEASE_SECONDS))).update(last_attempt_at=now):
        return
    status = ProviderStatus.objects.get(pk=provider_id)
    try:
        if status.collection_mode == 'api':
            from .codex_oauth import poll
            readings = poll(status)
        elif status.collection_mode == 'client':
            # Publish how the client is signed in before reading: the panel
            # shows that record, and it is useful even when the read fails.
            try:
                publish_client_auth_method()
            except Exception:
                logger.warning('No se ha podido publicar el estado de la sesión de Claude.')
            readings = client_readings()
        else:
            # Not connected: there is nothing to read.
            raise QuotaUnavailable()
        if not readings:
            raise QuotaUnavailable()
        observed = timezone.now()
        with transaction.atomic():
            # Conditional UPDATE locks this row until commit; a stale worker cannot overwrite a newer run.
            updated = ProviderStatus.objects.filter(pk=provider_id, refresh_token=token, refresh_expires_at__gt=observed).update(
                state=ProviderStatus.State.OK, used_percent=readings[0].used_percent,
                quota_label=readings[0].label,
                quotas=[r.as_json() for r in readings],
                last_success_at=observed, last_error='', consecutive_failures=0,
                refresh_token='', refresh_expires_at=None,
            )
            if updated:
                UsageLog.objects.bulk_create([UsageLog(
                    provider_id=provider_id, quota_key=r.key, quota_label=r.label,
                    used_percent=r.used_percent, observed_at=observed, reset_text=r.reset_text,
                ) for r in readings])
    except Exception as exc:
        failure = exc if isinstance(exc, ScrapeFailure) else ScrapeFailure()
        ProviderStatus.objects.filter(pk=provider_id, refresh_token=token).update(
            state=failure.state, last_error=failure.message,
            consecutive_failures=F('consecutive_failures') + 1,
            refresh_token='', refresh_expires_at=None,
        )
        logger.warning('Lectura fallida: provider=%s state=%s', status.provider, failure.state)

"""Admin flow to switch Claude's collection to the official client on the server.

The server asks the official Claude Code client for the subscription limits, so no
PC has to be running. The client authenticates itself with the claude.ai session it
keeps in its private configuration directory; TokenDash never receives or stores it.

That session lives in a private volume of the ``worker`` container, so the panel
(another service) cannot ask the client about it: the worker publishes the *kind*
of credential it uses and the panel reads that record.
"""
import json

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from dashboard.models import ProviderStatus
from .connection_views import check_operator
from .tasks import check_claude_session, enqueue_refresh


def client_available():
    """True when the server can run the official client."""
    from django.conf import settings
    from pathlib import Path
    import shutil
    if settings.CLAUDE_CLIENT_PATH:
        # An explicit path must exist; a stale one would only fail at query time.
        return Path(settings.CLAUDE_CLIENT_PATH).is_file()
    return bool(shutil.which('claude') or (Path.home() / '.local/bin/claude').is_file())


def client_session_state():
    """How the server's client is signed in, as published by the worker.

    Never raises: a missing record must not break the page. The record holds
    only the kind of credential, never the credential itself.
    """
    from .claude_client import CHECK_COMMAND, LOGIN_COMMAND, STATUS_COMMAND, describe_session
    status = ProviderStatus.objects.filter(provider='claude').first()
    method = status.client_auth_method if status else ''
    checked_at = status.client_auth_checked_at if status else None
    installed = client_available()
    if not method:
        return {'installed': installed, 'connected': False, 'method': None,
                'checked_at': None,
                'label': _('The server has not checked the Claude session yet.'),
                'command': LOGIN_COMMAND, 'status_command': STATUS_COMMAND, 'check_command': CHECK_COMMAND}
    label, connected = describe_session(method)
    if method == 'unavailable':
        installed = False
    return {'installed': installed, 'connected': connected, 'method': method,
            'checked_at': checked_at, 'label': label,
            'command': LOGIN_COMMAND, 'status_command': STATUS_COMMAND, 'check_command': CHECK_COMMAND}


@never_cache
def claude_client_mode(request):
    check_operator(request)
    if request.method != 'POST':
        return JsonResponse({'error': _('Use POST.')}, status=405)
    try:
        if len(request.body) > 4096:
            raise ValueError()
        action = json.loads(request.body).get('action')
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': _('Invalid request.')}, status=400)

    status = ProviderStatus.objects.get(provider='claude')

    if action == 'enable':
        if not client_available():
            return JsonResponse({'error': _('The official Claude Code client is not installed on the server. '
                                             'Rebuild the image or set CLAUDE_CLIENT_PATH in the .env.')}, status=409)
        session = client_session_state()
        with transaction.atomic():
            ProviderStatus.objects.filter(pk=status.pk).update(
                collection_mode='client', refresh_token='', refresh_expires_at=None, last_error='')
        try:
            enqueue_refresh(status.pk)
            message = _('The server is checking the claude.ai session and reading the Claude limits. '
                        'Wait a few seconds and reload this page.')
        except Exception:
            message = _('The server will read the Claude limits at the next automatic refresh. '
                        'If they do not appear, check that the account is connected on the server.')
        if not session['connected']:
            # The last published state does not say there is a usable session:
            # name the command instead of making the operator hunt for it.
            if session['method'] and session['method'] != 'unknown':
                message += ' ' + _('Connect it on the server with: %(command)s.') % {'command': session['command']}
            else:
                message += ' ' + _('If the quota does not appear, check the session on the server with: %(command)s.') % {
                    'command': session['command']}
            return JsonResponse({'message': message, 'needs_session': True, 'command': session['command']})
        return JsonResponse({'message': message})

    if action == 'check':
        try:
            check_claude_session.delay()
            message = _('The server is checking the claude.ai session. '
                        'Wait a few seconds and reload this page.')
        except Exception:
            message = _('The server will check it at the next automatic refresh.')
        return JsonResponse({'message': message})

    return JsonResponse({'error': _('Unknown action.')}, status=400)

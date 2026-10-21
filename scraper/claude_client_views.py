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
                'label': 'El servidor todavía no ha comprobado la sesión de Claude.',
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
        return JsonResponse({'error': 'Utiliza POST.'}, status=405)
    try:
        if len(request.body) > 4096:
            raise ValueError()
        action = json.loads(request.body).get('action')
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Solicitud no válida.'}, status=400)

    status = ProviderStatus.objects.get(provider='claude')

    if action == 'enable':
        if not client_available():
            return JsonResponse({'error': 'El servidor no tiene el cliente oficial de Claude Code instalado. '
                                           'Reconstruye la imagen o indica CLAUDE_CLIENT_PATH en el .env.'}, status=409)
        session = client_session_state()
        with transaction.atomic():
            ProviderStatus.objects.filter(pk=status.pk).update(
                collection_mode='client', refresh_token='', refresh_expires_at=None, last_error='')
        try:
            enqueue_refresh(status.pk)
            message = ('El servidor comprueba la sesión de claude.ai y lee los límites de Claude. '
                       'Espera unos segundos y vuelve a cargar esta página.')
        except Exception:
            message = ('El servidor consultará los límites de Claude en la próxima actualización automática. '
                       'Si no aparecen, comprueba que la cuenta esté conectada en el servidor.')
        if not session['connected']:
            # The last published state does not say there is a usable session:
            # name the command instead of making the operator hunt for it.
            if session['method'] and session['method'] != 'unknown':
                message += f' Conéctala en el servidor con: {session["command"]}.'
            else:
                message += (f' Si la cuota no aparece, comprueba la sesión en el servidor con: '
                            f'{session["command"]}.')
            return JsonResponse({'message': message, 'needs_session': True, 'command': session['command']})
        return JsonResponse({'message': message})

    if action == 'check':
        try:
            check_claude_session.delay()
            message = ('El servidor está comprobando la sesión de claude.ai. '
                       'Espera unos segundos y vuelve a cargar esta página.')
        except Exception:
            message = 'El servidor lo comprobará en la próxima actualización automática.'
        return JsonResponse({'message': message})

    return JsonResponse({'error': 'Acción desconocida.'}, status=400)

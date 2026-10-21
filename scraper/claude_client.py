"""Read Claude Code's subscription limits from the server.

The server runs the official Claude Code client and asks it for usage with the
experimental ``get_usage`` control request. Only control requests are sent: never a
user message, never a model prompt, and the client's stored credentials are never
read. The client authenticates itself with the session it holds in its own
configuration directory (the private ``claude_config`` volume).

A token from ``claude setup-token`` is not enough: Anthropic scopes that token to
model requests only, so the client cannot reach the usage endpoint with it. The
quota requires the session of a full claude.ai sign-in, which the client refreshes
on its own.

The protocol lives in ``claude_usage.py``, a standard-library module. The interface is experimental: any failure keeps the last valid
reading, so the dashboard never shows an invented percentage.
"""
import importlib.util
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .quotas import ScrapeFailure

logger = logging.getLogger(__name__)

HELPER = Path(__file__).with_name('claude_usage.py')
_module = None


class ClientUnavailable(ScrapeFailure):
    state = 'unavailable'
    message = 'El servidor no ha podido consultar la cuota de Claude. Se conserva la última lectura.'


def helper():
    """Load the protocol helper (once per process)."""
    global _module
    if _module is None:
        spec = importlib.util.spec_from_file_location('tokendash_claude_usage', HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module = module
    return _module


def find_executable(configured=None):
    """Locate the official client, honouring an explicit path first."""
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    return helper().find_executable()


def epoch(value):
    """ISO 8601 from the client -> epoch seconds, or None."""
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def auth_state(executable, timeout=45):
    """How the client is signed in, read with the official ``auth status``.

    Returns the ``authMethod`` string, or None when it cannot be determined.
    Only the kind of credential is read; no token, email or organization is kept.
    """
    environment = os.environ.copy()
    environment.pop('CLAUDECODE', None)
    try:
        finished = subprocess.run([str(executable), 'auth', 'status'], env=environment,
                                  capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    raw = (finished.stdout or '').strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if isinstance(data, dict):
        method = data.get('authMethod')
        if isinstance(method, str) and method:
            return method
    return None


def explain_missing_quota(executable=None, subscription_type=None):
    """A specific reason why the client published no quota windows."""
    client = executable or find_executable(settings.CLAUDE_CLIENT_PATH or None)
    method = auth_state(client) if client else None
    if method == 'claude.ai':
        return ('Claude Code está conectado a tu cuenta de claude.ai, pero no publica cuotas de '
                'suscripción. Puede que tu plan no las exponga.')
    if method == 'oauth_token':
        return ('El servidor usa un token de "claude setup-token", que Anthropic limita a las '
                'peticiones al modelo y no permite consultar la cuota. Inicia sesión con '
                '"claude auth login" en el servidor y quita CLAUDE_CODE_OAUTH_TOKEN del .env.')
    if method in ('api_key', 'api_key_helper', 'third_party'):
        return ('El servidor está autenticado con una clave de API. Ese tipo de credencial no '
                'publica cuotas de suscripción; hace falta una sesión de claude.ai.')
    if method == 'none':
        return ('El servidor no tiene ninguna sesión iniciada. Ejecuta "claude auth login" en el '
                'servidor para conectar la cuenta de claude.ai.')
    if subscription_type:
        return ('Claude Code no publicó cuotas de suscripción para la cuenta conectada.')
    return ('Claude Code no publicó cuotas de suscripción: la cuenta no está conectada con una '
            'suscripción de claude.ai.')


# How each sign-in method is described in the admin panel. Only the kind of
# credential is shown: never a token, an email or an organization.
AUTH_METHODS = {
    'claude.ai': ('Sesión de claude.ai conectada', True),
    'oauth_token': ('Token de "claude setup-token" (no puede leer la cuota)', False),
    'api_key': ('Clave de API (no publica cuotas)', False),
    'api_key_helper': ('Clave de API (no publica cuotas)', False),
    'third_party': ('Credencial de un tercero (no publica cuotas)', False),
    'none': ('Sin sesión iniciada', False),
    # The two states in which the client could not answer at all.
    'unavailable': ('El cliente oficial de Claude Code no está instalado en el servidor.', False),
    'unknown': ('No se ha podido comprobar el inicio de sesión del cliente en el servidor.', False),
}

# The console commands the operator may need. They act on the worker, which
# is the container that holds the client's session.
LOGIN_COMMAND = 'docker compose exec worker claude auth login'
STATUS_COMMAND = 'docker compose exec worker claude auth status'
CHECK_COMMAND = 'docker compose exec worker python manage.py claude_estado'


def describe_session(method):
    """Label and whether a credential can read the quota, for a known method."""
    return AUTH_METHODS.get(method, ('Método de acceso desconocido', False))


def current_auth_method():
    """The kind of credential the client uses here, as a string to publish.

    This must run where the client keeps its session (the worker): the
    configuration directory with the session is a private volume of that
    container. Only the kind of credential is read, never the credential.
    """
    client = find_executable(settings.CLAUDE_CLIENT_PATH or None)
    if client is None:
        return 'unavailable'
    method = auth_state(client)
    return method or 'unknown'


def session_state():
    """How the server's client is signed in, read in the worker.

    Returns a dict with the description of the credential, whether it can read
    the quota, and the two commands the operator may need. The client itself
    keeps the secret: this only reports the kind of credential, never it.
    """
    method = current_auth_method()
    label, connected = describe_session(method)
    return {'installed': method != 'unavailable', 'connected': connected, 'method': method,
            'label': label, 'command': LOGIN_COMMAND, 'status_command': STATUS_COMMAND}



def read_limits(executable=None, timeout=None):
    """Subscription windows as {'five_hour': .., 'seven_day': ..}.

    Raises ClientUnavailable when there is no new reading; the caller must then keep
    the previous one.
    """
    client = find_executable(executable or settings.CLAUDE_CLIENT_PATH or None)
    if client is None:
        raise ClientUnavailable('El cliente oficial de Claude Code no está instalado en el servidor.')
    try:
        result = helper().probe(client, timeout=timeout or settings.CLAUDE_CLIENT_TIMEOUT)
    except Exception as error:
        # Never log the client's output, its errors or its configuration.
        raise ClientUnavailable() from error
    if not result.get('ok'):
        raise ClientUnavailable(f'El cliente oficial de Claude Code no respondió a la consulta de uso (etapa {result.get("stage")}).')
    if not result.get('available'):
        raise ClientUnavailable(explain_missing_quota(client, result.get('subscription_type')))
    windows = result.get('windows') or {}
    if not windows:
        raise ClientUnavailable('Claude Code respondió sin ventanas de cuota utilizables.')
    return windows

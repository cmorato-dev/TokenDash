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
from django.utils.translation import gettext as _, gettext_noop

from .quotas import ScrapeFailure

logger = logging.getLogger(__name__)

HELPER = Path(__file__).with_name('claude_usage.py')
_module = None


class ClientUnavailable(ScrapeFailure):
    state = 'unavailable'
    message = gettext_noop('The server could not read the Claude quota. The last reading is kept.')


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
    """A specific reason why the client published no quota windows (in English, translated when shown)."""
    client = executable or find_executable(settings.CLAUDE_CLIENT_PATH or None)
    method = auth_state(client) if client else None
    if method == 'claude.ai':
        return gettext_noop('Claude Code is connected to your claude.ai account, but it publishes no '
                            'subscription quotas. Your plan may not expose them.')
    if method == 'oauth_token':
        return gettext_noop('The server uses a token from "claude setup-token", which Anthropic limits to '
                            'model requests and which cannot read the quota. Sign in with '
                            '"claude auth login" on the server and remove CLAUDE_CODE_OAUTH_TOKEN from the .env.')
    if method in ('api_key', 'api_key_helper', 'third_party'):
        return gettext_noop('The server is signed in with an API key. That kind of credential publishes '
                            'no subscription quotas; a claude.ai session is needed.')
    if method == 'none':
        return gettext_noop('The server is not signed in. Run "claude auth login" on the '
                            'server to connect the claude.ai account.')
    if subscription_type:
        return gettext_noop('Claude Code published no subscription quotas for the connected account.')
    return gettext_noop('Claude Code published no subscription quotas: the account is not connected to a '
                        'claude.ai subscription.')


# How each sign-in method is described in the admin panel. Only the kind of
# credential is shown: never a token, an email or an organization.
AUTH_METHODS = {
    'claude.ai': (gettext_noop('claude.ai session connected'), True),
    'oauth_token': (gettext_noop('Token from "claude setup-token" (cannot read the quota)'), False),
    'api_key': (gettext_noop('API key (publishes no quotas)'), False),
    'api_key_helper': (gettext_noop('API key (publishes no quotas)'), False),
    'third_party': (gettext_noop('Third-party credential (publishes no quotas)'), False),
    'none': (gettext_noop('Not signed in'), False),
    # The two states in which the client could not answer at all.
    'unavailable': (gettext_noop('The official Claude Code client is not installed on the server.'), False),
    'unknown': (gettext_noop("The client's sign-in could not be checked on the server."), False),
}

# The console commands the operator may need. They act on the worker, which
# is the container that holds the client's session.
LOGIN_COMMAND = 'docker compose exec worker claude auth login'
STATUS_COMMAND = 'docker compose exec worker claude auth status'
CHECK_COMMAND = 'docker compose exec worker python manage.py claude_status'


def describe_session(method):
    """Label, in the active language, and whether a credential can read the quota."""
    label, connected = AUTH_METHODS.get(method, (gettext_noop('Unknown sign-in method'), False))
    return _(label), connected


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
        raise ClientUnavailable(gettext_noop('The official Claude Code client is not installed on the server.'))
    try:
        result = helper().probe(client, timeout=timeout or settings.CLAUDE_CLIENT_TIMEOUT)
    except Exception as error:
        # Never log the client's output, its errors or its configuration.
        raise ClientUnavailable() from error
    if not result.get('ok'):
        logger.warning('The Claude Code client did not answer the usage request: stage=%s', result.get('stage'))
        raise ClientUnavailable(gettext_noop('The official Claude Code client did not answer the usage request.'))
    if not result.get('available'):
        raise ClientUnavailable(explain_missing_quota(client, result.get('subscription_type')))
    windows = result.get('windows') or {}
    if not windows:
        raise ClientUnavailable(gettext_noop('Claude Code answered without usable quota windows.'))
    return windows

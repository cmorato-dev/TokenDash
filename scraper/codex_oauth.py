"""Sign in with a ChatGPT account (Codex OAuth) and read the Codex usage limits server-side.

These are the endpoints used by the open-source Codex CLI to show its 5-hour and weekly
limits. They are not a documented public API and may change; any failure keeps the last
valid reading. Tokens are stored encrypted with a key derived from DJANGO_SECRET_KEY and
are only sent to auth.openai.com and chatgpt.com.
"""
import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_noop
from django.views.decorators.debug import sensitive_variables

from .quotas import (QuotaUnavailable, ScrapeFailure, SessionExpired, VerificationRequired,  # noqa: F401  (re-exported)
                     quota_reading, readings_from_windows, window_key)

logger = logging.getLogger(__name__)
ISSUER = 'https://auth.openai.com'
CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'
REDIRECT_URI = 'http://localhost:1455/auth/callback'
USAGE_URL = 'https://chatgpt.com/backend-api/wham/usage'
USER_AGENT = 'TokenDash/1.0 (self-hosted usage monitor)'
LOGIN_MAX_AGE = timedelta(minutes=15)


class AuthExpired(SessionExpired):
    message = gettext_noop('The connection with ChatGPT has expired. Sign in again in "Connect accounts".')


class ProviderBlocked(VerificationRequired):
    message = gettext_noop('ChatGPT refused the usage request from the server. The latest data is kept.')


class NetworkFailure(ScrapeFailure):
    message = gettext_noop('ChatGPT could not be reached. It will be retried automatically.')


class LoginError(Exception):
    """Raised while the operator signs in, so its message is already translated."""


def _fernet():
    digest = hashlib.sha256(b'tokendash.credentials.v1:' + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


@sensitive_variables('tokens')
def encrypt(tokens):
    return _fernet().encrypt(json.dumps(tokens).encode()).decode()


def decrypt(secret):
    try:
        return json.loads(_fernet().decrypt(secret.encode()))
    except (InvalidToken, ValueError):
        # DJANGO_SECRET_KEY changed or data is corrupt: the user must sign in again.
        raise AuthExpired() from None


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def jwt_claims(token):
    """Decode claims of a token received directly from the issuer over TLS (not a trust decision)."""
    try:
        part = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    except (IndexError, ValueError, AttributeError):
        return {}


def new_login():
    verifier = b64url(secrets.token_bytes(64))
    state = b64url(secrets.token_bytes(32))
    query = urlencode({
        'response_type': 'code', 'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI,
        'scope': 'openid profile email offline_access',
        'code_challenge': b64url(hashlib.sha256(verifier.encode()).digest()), 'code_challenge_method': 'S256',
        'id_token_add_organizations': 'true', 'codex_cli_simplified_flow': 'true',
        'state': state, 'originator': 'codex_cli_rs',
    })
    return f'{ISSUER}/oauth/authorize?{query}', verifier, state


def parse_callback(text):
    """Accept the address shown by the browser after authorizing (or just its query string)."""
    text = (text or '').strip()
    if len(text) > 4000:
        raise LoginError(_('The pasted address is too long.'))
    parsed = urlparse(text if '://' in text else 'http://localhost/?' + text.lstrip('?'))
    if parsed.hostname not in ('localhost', '127.0.0.1') or (parsed.path and parsed.path not in ('/', '/auth/callback')):
        raise LoginError(_('Paste the full address of the tab, which starts with http://localhost:1455/auth/callback.'))
    query = parse_qs(parsed.query)
    if query.get('error'):
        raise LoginError(_('ChatGPT did not authorise the access. Try again.'))
    code, state = (query.get('code') or [''])[0], (query.get('state') or [''])[0]
    if not code or not state:
        raise LoginError(_('The pasted address does not contain the authorisation code.'))
    return code, state


@sensitive_variables('form', 'body', 'headers')
def http_json(method, url, *, form=None, body=None, headers=None):
    """Return (status, data). Response bodies are never logged: they may contain tokens."""
    data, request_headers = None, {'Accept': 'application/json', 'User-Agent': USER_AGENT, **(headers or {})}
    if form is not None:
        data = urlencode(form).encode()
        request_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        data = json.dumps(body).encode()
        request_headers['Content-Type'] = 'application/json'
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            status, raw, kind = response.status, response.read(200000), response.headers.get('Content-Type', '')
    except HTTPError as exc:
        status, raw, kind = exc.code, exc.read(200000), exc.headers.get('Content-Type', '') if exc.headers else ''
    except (URLError, TimeoutError, OSError):
        raise NetworkFailure() from None
    if 'json' not in kind:
        return status, None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


@sensitive_variables('code', 'verifier', 'data')
def exchange_code(code, verifier):
    status, data = http_json('POST', f'{ISSUER}/oauth/token', form={
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID, 'code_verifier': verifier,
    })
    if status != 200 or not isinstance(data, dict) or not data.get('access_token') or not data.get('refresh_token'):
        logger.warning('Codex OAuth exchange refused: status=%s', status)
        raise LoginError(_('ChatGPT did not accept the code. Codes expire in a few minutes: sign in again and paste the address straight away.'))
    return tokens_from_response(data)


def tokens_from_response(data, previous=None):
    previous = previous or {}
    tokens = {
        'access_token': data.get('access_token') or previous.get('access_token'),
        'refresh_token': data.get('refresh_token') or previous.get('refresh_token'),
        'id_token': data.get('id_token') or previous.get('id_token', ''),
    }
    auth = jwt_claims(tokens['id_token']).get('https://api.openai.com/auth') or {}
    access_auth = jwt_claims(tokens['access_token']).get('https://api.openai.com/auth') or {}
    tokens['account_id'] = auth.get('chatgpt_account_id') or access_auth.get('chatgpt_account_id') or previous.get('account_id', '')
    tokens['plan_type'] = str(auth.get('chatgpt_plan_type') or access_auth.get('chatgpt_plan_type') or previous.get('plan_type', ''))[:40]
    return tokens


def access_expiry(tokens):
    exp = jwt_claims(tokens.get('access_token', '')).get('exp')
    return datetime.fromtimestamp(exp, dt_timezone.utc) if isinstance(exp, (int, float)) else None


def save_credential(status, tokens):
    from .models import ProviderCredential
    ProviderCredential.objects.update_or_create(provider=status, defaults={
        'secret': encrypt(tokens), 'plan_type': tokens.get('plan_type', ''), 'access_expires_at': access_expiry(tokens),
    })


@sensitive_variables('tokens', 'data')
def refresh_tokens(status, tokens):
    code, data = http_json('POST', f'{ISSUER}/oauth/token', body={
        'client_id': CLIENT_ID, 'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token'],
        'scope': 'openid profile email',
    })
    if code in (400, 401) or (code == 200 and not (isinstance(data, dict) and data.get('access_token'))):
        raise AuthExpired()
    if code != 200:
        raise ProviderBlocked() if code in (403, 429) else NetworkFailure()
    tokens = tokens_from_response(data, tokens)
    save_credential(status, tokens)  # Refresh tokens rotate: persist before using them.
    return tokens


def readings_from_usage(payload):
    limits = (payload or {}).get('rate_limit') if isinstance(payload, dict) else None
    windows = []
    for name in ('primary_window', 'secondary_window'):
        window = (limits or {}).get(name)
        if isinstance(window, dict) and window.get('limit_window_seconds'):
            windows.append({'used_percent': window.get('used_percent'),
                            'window_minutes': window['limit_window_seconds'] / 60,
                            'resets_at': window.get('reset_at')})
    readings = readings_from_windows(windows)
    if not readings:
        raise QuotaUnavailable()
    return readings


@sensitive_variables('tokens', 'data')
def poll(status):
    from .models import ProviderCredential
    credential = ProviderCredential.objects.filter(provider=status).first()
    if credential is None:
        raise AuthExpired()
    tokens = decrypt(credential.secret)
    expiry = access_expiry(tokens)
    if expiry is None or expiry < timezone.now() + timedelta(minutes=5):
        tokens = refresh_tokens(status, tokens)
    for attempt in range(2):
        headers = {'Authorization': f"Bearer {tokens['access_token']}"}
        if tokens.get('account_id'):
            headers['ChatGPT-Account-Id'] = tokens['account_id']
        code, data = http_json('GET', USAGE_URL, headers=headers)
        if code == 401 and attempt == 0:
            tokens = refresh_tokens(status, tokens)
            continue
        if code == 401:
            raise AuthExpired()
        if code in (403, 429) or (code == 200 and not isinstance(data, dict)):
            raise ProviderBlocked()
        if code != 200:
            raise NetworkFailure()
        if data.get('plan_type') and data['plan_type'] != credential.plan_type:
            ProviderCredential.objects.filter(pk=credential.pk).update(plan_type=str(data['plan_type'])[:40])
        return readings_from_usage(data)
    raise AuthExpired()

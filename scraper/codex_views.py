"""Admin flow to connect a ChatGPT account through the Codex sign-in page."""
import hmac
import json
from datetime import datetime

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from dashboard.models import ProviderStatus
from . import codex_oauth
from .connection_views import check_operator
from .models import ProviderCredential
from .tasks import enqueue_refresh

SESSION_KEY = 'codex_oauth_login'


@sensitive_variables('payload', 'pending', 'code', 'tokens', 'verifier')
@sensitive_post_parameters()
@never_cache
def codex_login(request):
    check_operator(request)
    if request.method != 'POST':
        return JsonResponse({'error': _('Use POST.')}, status=405)
    try:
        if len(request.body) > 8000:
            raise ValueError()
        payload = json.loads(request.body)
        action = payload.get('action')
    except (ValueError, AttributeError):
        return JsonResponse({'error': _('Invalid request.')}, status=400)
    status = ProviderStatus.objects.get(provider='chatgpt')

    if action == 'start':
        url, verifier, state = codex_oauth.new_login()
        request.session[SESSION_KEY] = {'verifier': verifier, 'state': state, 'created': timezone.now().isoformat()}
        return JsonResponse({'url': url, 'message': _('The ChatGPT sign-in has opened in another tab. When you finish, copy the address of that tab and paste it here.')})

    if action == 'complete':
        pending = request.session.get(SESSION_KEY)
        if not pending or timezone.now() - datetime.fromisoformat(pending['created']) > codex_oauth.LOGIN_MAX_AGE:
            return JsonResponse({'error': _('The sign-in has expired. Press "Sign in with ChatGPT" again.')}, status=409)
        try:
            code, state = codex_oauth.parse_callback(payload.get('callback'))
            if not hmac.compare_digest(state, pending['state']):
                raise codex_oauth.LoginError(_('The pasted address does not belong to this sign-in. Start again.'))
            tokens = codex_oauth.exchange_code(code, pending['verifier'])
        except codex_oauth.LoginError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        except codex_oauth.NetworkFailure as exc:
            return JsonResponse({'error': _(exc.message)}, status=502)
        request.session.pop(SESSION_KEY, None)
        with transaction.atomic():
            codex_oauth.save_credential(status, tokens)
            ProviderStatus.objects.filter(pk=status.pk).update(collection_mode='api', refresh_token='', refresh_expires_at=None, last_error='')
        try:
            enqueue_refresh(status.pk)
            message = _('ChatGPT connected. The Codex limits are being read; after that they refresh on their own.')
        except Exception:
            message = _('ChatGPT connected. The queue is not available now; the limits will be read at the next refresh.')
        return JsonResponse({'message': message, 'plan_type': tokens.get('plan_type', '')})

    if action == 'disconnect':
        with transaction.atomic():
            ProviderCredential.objects.filter(provider=status).delete()
            ProviderStatus.objects.filter(pk=status.pk, collection_mode='api').update(collection_mode='none')
        request.session.pop(SESSION_KEY, None)
        return JsonResponse({'message': _('ChatGPT disconnected and its credential deleted from TokenDash. Earlier readings are kept.')})

    return JsonResponse({'error': _('Unknown action.')}, status=400)

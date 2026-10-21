from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from dashboard.models import ProviderStatus, RefreshSettings
from .models import ProviderCredential

def check_operator(request):
    if not (request.user.is_active and request.user.is_staff and request.user.is_superuser):
        raise PermissionDenied('Solo el administrador principal puede conectar cuentas.')

@never_cache
def connections(request):
    check_operator(request)
    from .claude_client_views import client_session_state
    return render(request, 'admin/scraper/connections.html', {
        **admin.site.each_context(request), 'title': 'Conectar cuentas de IA',
        'interval_minutes': RefreshSettings.load().refresh_minutes,
        'chatgpt': ProviderStatus.objects.get(provider='chatgpt'),
        'codex_credential': ProviderCredential.objects.filter(provider__provider='chatgpt').first(),
        'claude': ProviderStatus.objects.get(provider='claude'),
        'claude_session': client_session_state(),
    })

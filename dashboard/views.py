from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Avg
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek, TruncYear
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View, csrf
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView

from .models import IntegrationKey, ProviderStatus, UsageLog
from scraper.tasks import enqueue_refresh

def provider_hint(status):
    """What to do when a provider still has no reading.

    The text names the next step that actually unblocks it, and for the
    server-side Claude client it also names the console command.
    """
    if status.provider == 'claude':
        if status.collection_mode == 'client':
            return ('El servidor necesita una sesión de claude.ai para leer la cuota: conéctala desde '
                    '«Conectar cuentas» o, por consola, con '
                    '"docker compose exec worker claude auth login".')
        return ('Conecta Claude en «Conectar cuentas» para que el servidor lea sus límites con el '
                'cliente oficial de Claude Code.')
    if status.provider == 'chatgpt':
        if status.collection_mode == 'api':
            # The credential exists: the limits are read on the next refresh.
            return 'Pulsa «Actualizar ahora» para leer los límites de Codex.'
        return 'Conecta ChatGPT en «Conectar cuentas» para leer los límites de Codex.'
    return ''

# Windows offered in «Evolución de los límites»: days, label and the granularity
# used to group the readings. Long windows are grouped by week, month or year, so
# the chart never needs one point per day (five years would be more than 1800).
PERIODS = {
    7: ('7 días', 'day'),
    30: ('30 días', 'day'),
    90: ('3 meses', 'week'),
    182: ('6 meses', 'week'),
    365: ('1 año', 'month'),
    1825: ('5 años', 'year'),
}
TRUNCATIONS = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth, 'year': TruncYear}


def can_refresh(status):
    if status.collection_mode == 'api':
        return hasattr(status, 'credential')
    if status.collection_mode == 'client':
        # The official client runs on the server; it only needs its own credentials.
        from scraper.claude_client_views import client_available
        return client_available()
    return False


def serialize_status(status):
    now = timezone.now()
    quotas = []
    for quota in status.quotas:
        quota = dict(quota)
        # The window restarted after this reading: the value is the last known one, not the current one.
        quota['window_reset'] = bool(quota.get('resets_at') and quota['resets_at'] < now.isoformat())
        quotas.append(quota)
    refreshable = can_refresh(status)
    return {
        'provider': status.provider, 'name': status.get_provider_display(),
        'collection_mode': status.collection_mode,
        'state': status.state, 'state_label': status.get_state_display(),
        'used_percent': float(status.used_percent) if status.used_percent is not None else None,
        'available_percent': float(status.available_percent) if status.available_percent is not None else None,
        'quota_label': status.quota_label, 'quotas': quotas,
        'can_refresh': refreshable,
        'hint': '' if status.last_success_at or refreshable else provider_hint(status),
        'last_success_at': status.last_success_at, 'last_attempt_at': status.last_attempt_at,
        'last_error': status.last_error,
        'refreshing': bool(status.refresh_token and status.refresh_expires_at and status.refresh_expires_at > now),
    }

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['providers'] = ProviderStatus.objects.all()
        return context

def integration_key(request):
    """The Home Assistant key sent as «Authorization: Bearer …», if it is valid."""
    scheme, _, key = request.headers.get('Authorization', '').partition(' ')
    if scheme.lower() != 'bearer' or not key.strip():
        return None
    record = IntegrationKey.objects.filter(key_hash=IntegrationKey.digest(key.strip())).first()
    if record:
        # Modules poll every 30 seconds: note the use only every few minutes.
        now = timezone.now()
        if not record.last_used_at or record.last_used_at < now - timedelta(minutes=5):
            IntegrationKey.objects.filter(pk=record.pk).update(last_used_at=now)
    return record


class LoginOrKeyRequiredMixin:
    """Read-only views open to a signed-in user or to a Home Assistant key."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated or integration_key(request):
            return super().dispatch(request, *args, **kwargs)
        if 'Authorization' in request.headers:
            return JsonResponse({'error': 'La clave de Home Assistant no es válida o se ha borrado.'}, status=401)
        return redirect_to_login(request.get_full_path())


class StatusView(LoginOrKeyRequiredMixin, View):
    def get(self, request):
        response = JsonResponse({'providers': [serialize_status(s) for s in ProviderStatus.objects.select_related('credential')]})
        response['Cache-Control'] = 'no-store'
        return response

class RefreshView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return JsonResponse({'error': 'Tu usuario no puede pedir actualizaciones.'}, status=403)
        return super().handle_no_permission()

    def post(self, request, provider):
        status = ProviderStatus.objects.filter(provider=provider).first()
        if status is None:
            return JsonResponse({'error': 'Proveedor desconocido.'}, status=404)
        if status.collection_mode == 'api' and not hasattr(status, 'credential'):
            return JsonResponse({'error': 'Vuelve a conectar la cuenta en «Conectar cuentas».'}, status=409)
        if status.collection_mode == 'client' and not can_refresh(status):
            return JsonResponse({'error': 'El servidor no tiene el cliente oficial de Claude Code instalado.'}, status=409)
        if status.collection_mode == 'none':
            return JsonResponse({'error': 'Esta cuenta no tiene una fuente de cuota conectada.'}, status=409)
        # An atomic cooldown also applies to failed runs and concurrent requests.
        if status.last_attempt_at and status.last_attempt_at > timezone.now() - timedelta(seconds=60):
            return JsonResponse({'error': 'Espera un minuto antes de volver a actualizar.'}, status=429)
        try:
            token = enqueue_refresh(status.pk)
        except Exception:
            return JsonResponse({'error': 'La cola no está disponible. Revisa Redis y el worker.'}, status=503)
        return JsonResponse({'queued': bool(token), 'message': 'Actualización encolada.' if token else 'Ya hay una actualización en curso.'}, status=202)

def bucket_starts(start, today, granularity):
    """First day of every bucket between ``start`` and ``today`` (inclusive).

    The buckets match the truncation used in the query: a day, the Monday of a
    week, the first of a month or the first of a year.
    """
    if granularity == 'day':
        current = start
        while current <= today:
            yield current
            current += timedelta(days=1)
    elif granularity == 'week':
        current = start - timedelta(days=start.weekday())
        while current <= today:
            yield current
            current += timedelta(days=7)
    elif granularity == 'month':
        current = start.replace(day=1)
        while current <= today:
            yield current
            current = (current + timedelta(days=32)).replace(day=1)
    else:
        current = start.replace(month=1, day=1)
        while current <= today:
            yield current
            current = current.replace(year=current.year + 1)


class HistoryView(LoginOrKeyRequiredMixin, View):
    def get(self, request):
        try:
            days = int(request.GET.get('days', '7'))
        except ValueError:
            return JsonResponse({'error': 'Periodo inválido.'}, status=400)
        if days not in PERIODS:
            return JsonResponse({'error': 'Elige uno de los periodos disponibles.'}, status=400)
        label, granularity = PERIODS[days]
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        # A datetime bound keeps the query on the observed_at index.
        start_at = timezone.make_aware(datetime.combine(start, time.min))
        rows = UsageLog.objects.filter(observed_at__gte=start_at).annotate(
            bucket=TRUNCATIONS[granularity]('observed_at')).values(
            'provider__provider', 'quota_key', 'bucket',
        ).annotate(used=Avg('used_percent')).order_by('bucket')
        labels = [day.isoformat() for day in bucket_starts(start, today, granularity)]
        positions = {label: index for index, label in enumerate(labels)}
        series = {}
        for row in rows:
            key = (row['provider__provider'], row['quota_key'])
            values = series.setdefault(key, [None] * len(labels))
            index = positions.get(row['bucket'].date().isoformat())
            if index is not None:
                values[index] = float(Decimal(row['used']).quantize(Decimal('0.01')))
        response = JsonResponse({'labels': labels, 'granularity': granularity, 'period': label, 'series': [
            {'provider': key[0], 'quota': key[1], 'values': values} for key, values in series.items()
        ]})
        response['Cache-Control'] = 'no-store'
        return response


# Modules Home Assistant can show, each on its own page.
EMBED_MODULES = ('chatgpt', 'claude', 'grafica')


@method_decorator(xframe_options_exempt, name='dispatch')
class EmbedView(TemplateView):
    """One dashboard module alone, to show inside a Home Assistant card.

    The page carries no data: its script reads the key from the URL fragment
    (#clave=…), which the browser never sends to the server, and asks the
    read-only API with it. It has no buttons, so framing it is harmless.
    """
    template_name = 'dashboard/embed.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = kwargs['module']
        if module not in EMBED_MODULES:
            raise Http404
        context['module'] = module
        if module != 'grafica':
            context['provider'] = ProviderStatus.objects.filter(provider=module).first()
            if context['provider'] is None:
                raise Http404
        return context


def window_name(key):
    """«session» or «weekly»: Claude calls its weekly window weekly_all."""
    return 'weekly' if key in ('weekly', 'weekly_all') else key


class SensorView(LoginOrKeyRequiredMixin, View):
    """One provider's limits as flat values, for Home Assistant REST sensors."""

    def get(self, request, provider):
        status = ProviderStatus.objects.select_related('credential').filter(provider=provider).first()
        if status is None:
            return JsonResponse({'error': 'Proveedor desconocido.'}, status=404)
        data = serialize_status(status)
        result = {key: data[key] for key in ('provider', 'name', 'state', 'state_label', 'used_percent',
                                             'available_percent', 'last_success_at', 'last_attempt_at')}
        # Absent windows stay null: «no data» is never reported as 0 %.
        for name in ('session', 'weekly'):
            result.update({f'{name}_used_percent': None, f'{name}_resets_at': None, f'{name}_window_reset': None})
        for quota in data['quotas']:
            name = window_name(quota['key'])
            if name in ('session', 'weekly') and result[f'{name}_used_percent'] is None:
                result[f'{name}_used_percent'] = float(quota['used_percent'])
                result[f'{name}_resets_at'] = quota.get('resets_at')
                result[f'{name}_window_reset'] = quota['window_reset']
        response = JsonResponse(result)
        response['Cache-Control'] = 'no-store'
        return response


def csrf_failure(request, reason=''):
    # The dashboard reads the API with fetch(); an HTML page would only show as a JSON error.
    if request.path.startswith('/api/'):
        return JsonResponse({'error': 'La página ha caducado. Recárgala e inténtalo de nuevo.'}, status=403)
    return csrf.csrf_failure(request, reason)

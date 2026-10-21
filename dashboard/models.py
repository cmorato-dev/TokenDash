import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

PERCENT_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]

class ProviderStatus(models.Model):
    class Provider(models.TextChoices):
        CHATGPT = 'chatgpt', 'ChatGPT'
        CLAUDE = 'claude', 'Claude'

    class State(models.TextChoices):
        PENDING = 'pending', _('No data')
        OK = 'ok', _('Updated')
        EXPIRED = 'expired', _('Session expired, sign in again')
        BLOCKED = 'blocked', _('Manual verification required')
        UNAVAILABLE = 'unavailable', _('A quota of this account could not be read')
        ERROR = 'error', _('Refresh error')

    provider = models.CharField(_('provider'), max_length=20, choices=Provider.choices, unique=True)
    collection_mode = models.CharField(_('source'), max_length=12, choices=[('none', _('Not connected')), ('api', _('Connected account')), ('client', _('Official client on the server'))], default='none')
    # The kind of credential the server's official client uses (claude.ai, none,
    # oauth_token, api_key...). Only the kind: never the credential itself.
    # The worker writes it, because that is where the client's session lives:
    # the panel reads the record instead of running the client itself.
    client_auth_method = models.CharField(max_length=20, blank=True)
    client_auth_checked_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(_('state'), max_length=20, choices=State.choices, default=State.PENDING)
    used_percent = models.DecimalField(_('used %'), max_digits=5, decimal_places=2, null=True, blank=True, validators=PERCENT_VALIDATORS)
    quota_label = models.CharField(_('limit'), max_length=120, blank=True)
    quotas = models.JSONField(default=list, blank=True)
    last_attempt_at = models.DateTimeField(_('last attempt'), null=True, blank=True)
    last_success_at = models.DateTimeField(_('last valid reading'), null=True, blank=True)
    # The message in English; it is translated when shown.
    last_error = models.CharField(_('last error'), max_length=250, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    # Atomic lease shared by periodic and manual refreshes, including broker queue time.
    refresh_token = models.CharField(max_length=36, blank=True)
    refresh_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['provider']
        verbose_name = _('provider status')
        verbose_name_plural = _('provider statuses')
        constraints = [models.CheckConstraint(
            condition=models.Q(used_percent__isnull=True) | models.Q(used_percent__gte=0, used_percent__lte=100),
            name='status_percent_range',
        )]

    @property
    def available_percent(self):
        return None if self.used_percent is None else 100 - self.used_percent

    def __str__(self):
        return self.get_provider_display()


class UsageLog(models.Model):
    provider = models.ForeignKey(ProviderStatus, on_delete=models.CASCADE, related_name='usage_logs', verbose_name=_('provider'))
    quota_key = models.SlugField(_('limit key'), max_length=80)
    quota_label = models.CharField(_('limit'), max_length=120)
    used_percent = models.DecimalField(_('used %'), max_digits=5, decimal_places=2, validators=PERCENT_VALIDATORS)
    observed_at = models.DateTimeField(_('read at'), db_index=True)
    reset_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-observed_at']
        verbose_name = _('reading')
        verbose_name_plural = _('reading history')
        indexes = [models.Index(fields=['provider', 'quota_key', 'observed_at'])]
        constraints = [models.CheckConstraint(
            condition=models.Q(used_percent__gte=0, used_percent__lte=100), name='usage_percent_range',
        )]

    def __str__(self):
        return f'{self.provider}: {self.quota_label} {self.used_percent}%'


class IntegrationKey(models.Model):
    """Read-only access for Home Assistant: the modules and the sensor endpoints.

    Only the SHA-256 of the key is stored; the key itself is shown once, when it
    is created in the admin.
    """
    name = models.CharField(_('name'), max_length=80)
    prefix = models.CharField(_('key start'), max_length=12, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(_('created'), auto_now_add=True)
    last_used_at = models.DateTimeField(_('last used'), null=True, blank=True, editable=False)

    class Meta:
        ordering = ['name']
        verbose_name = _('Home Assistant key')
        verbose_name_plural = _('Home Assistant keys')

    @staticmethod
    def digest(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def generate(self):
        """Give this record a new key and return it; the caller shows it once."""
        key = 'td_' + secrets.token_urlsafe(32)
        self.prefix, self.key_hash = key[:10], self.digest(key)
        return key

    def __str__(self):
        return self.name


class RefreshSettings(models.Model):
    """How often the server reads the limits. A single row, edited in the admin."""
    INTERVALS = [
        (15, _('Every 15 minutes')), (20, _('Every 20 minutes')), (30, _('Every 30 minutes')), (45, _('Every 45 minutes')),
        (60, _('Every hour')), (120, _('Every 2 hours')), (180, _('Every 3 hours')), (360, _('Every 6 hours')),
    ]
    refresh_minutes = models.PositiveSmallIntegerField(
        _('refresh frequency'), choices=INTERVALS, default=20,
        help_text=_('How often the server reads the limits. The change applies from the next minute.'))
    last_scheduled_at = models.DateTimeField(_('last automatic refresh'), null=True, blank=True, editable=False)
    # Many people pay for only one subscription: the other card is hidden and never read.
    ACCOUNTS = [('both', _('ChatGPT and Claude')), ('chatgpt', _('Only ChatGPT')), ('claude', _('Only Claude'))]
    accounts = models.CharField(
        _('accounts you use'), max_length=10, choices=ACCOUNTS, default='both',
        help_text=_('If you only pay for one of the two subscriptions, the dashboard shows only that card and the server only reads that account.'))

    class Meta:
        verbose_name = _('settings')
        verbose_name_plural = _('settings')

    def __str__(self):
        return str(_('Settings'))

    @classmethod
    def load(cls):
        # The first value comes from SCRAPE_INTERVAL_MINUTES, for installations that set it in the .env.
        initial = settings.SCRAPE_INTERVAL_MINUTES
        if initial not in dict(cls.INTERVALS):
            initial = 20
        return cls.objects.get_or_create(pk=1, defaults={'refresh_minutes': initial})[0]

    @classmethod
    def shown_providers(cls):
        """The providers chosen in the settings: ``['chatgpt']``, ``['claude']`` or both."""
        accounts = cls.load().accounts
        return ['chatgpt', 'claude'] if accounts == 'both' else [accounts]

    @property
    def next_refresh_at(self):
        if self.last_scheduled_at is None:
            return None
        return self.last_scheduled_at + timedelta(minutes=self.refresh_minutes)

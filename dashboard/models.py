import hashlib
import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

PERCENT_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]

class ProviderStatus(models.Model):
    class Provider(models.TextChoices):
        CHATGPT = 'chatgpt', 'ChatGPT'
        CLAUDE = 'claude', 'Claude'

    class State(models.TextChoices):
        PENDING = 'pending', 'Sin datos'
        OK = 'ok', 'Actualizado'
        EXPIRED = 'expired', 'Sesión expirada, reautenticar'
        BLOCKED = 'blocked', 'Verificación manual requerida'
        UNAVAILABLE = 'unavailable', 'No se ha podido leer una cuota de esta cuenta'
        ERROR = 'error', 'Error de actualización'

    provider = models.CharField(max_length=20, choices=Provider.choices, unique=True)
    collection_mode = models.CharField(max_length=12, choices=[('none', 'Sin conectar'), ('api', 'Cuenta conectada'), ('client', 'Cliente oficial en el servidor')], default='none')
    # The kind of credential the server's official client uses (claude.ai, none,
    # oauth_token, api_key...). Only the kind: never the credential itself.
    # The worker writes it, because that is where the client's session lives:
    # the panel reads the record instead of running the client itself.
    client_auth_method = models.CharField(max_length=20, blank=True)
    client_auth_checked_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    used_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PERCENT_VALIDATORS)
    quota_label = models.CharField(max_length=120, blank=True)
    quotas = models.JSONField(default=list, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=250, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    # Atomic lease shared by periodic and manual refreshes, including broker queue time.
    refresh_token = models.CharField(max_length=36, blank=True)
    refresh_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['provider']
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
    provider = models.ForeignKey(ProviderStatus, on_delete=models.CASCADE, related_name='usage_logs')
    quota_key = models.SlugField(max_length=80)
    quota_label = models.CharField(max_length=120)
    used_percent = models.DecimalField(max_digits=5, decimal_places=2, validators=PERCENT_VALIDATORS)
    observed_at = models.DateTimeField(db_index=True)
    reset_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-observed_at']
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
    name = models.CharField('nombre', max_length=80)
    prefix = models.CharField('inicio de la clave', max_length=12, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField('creada', auto_now_add=True)
    last_used_at = models.DateTimeField('último uso', null=True, blank=True, editable=False)

    class Meta:
        ordering = ['name']
        verbose_name = 'clave de Home Assistant'
        verbose_name_plural = 'claves de Home Assistant'

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

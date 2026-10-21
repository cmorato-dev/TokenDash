from django.db import models


class ProviderCredential(models.Model):
    """OAuth tokens for reading a provider's usage limits, encrypted at rest (see codex_oauth)."""
    provider = models.OneToOneField('dashboard.ProviderStatus', on_delete=models.CASCADE, related_name='credential')
    secret = models.TextField()
    plan_type = models.CharField(max_length=40, blank=True)
    access_expires_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Credencial de {self.provider}'

from django.contrib import admin
from django.contrib.auth.models import Group
from django.template.response import TemplateResponse
from django.urls import reverse

from .models import IntegrationKey, ProviderStatus, UsageLog
from .views import EMBED_MODULES

# Only the user list is needed: TokenDash has no permission groups.
admin.site.unregister(Group)

@admin.register(ProviderStatus)
class ProviderStatusAdmin(admin.ModelAdmin):
    list_display = ('provider', 'state', 'used_percent', 'last_success_at', 'last_attempt_at')
    readonly_fields = [field.name for field in ProviderStatus._meta.fields]

@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ('provider', 'quota_label', 'used_percent', 'observed_at')
    list_filter = ('provider', 'quota_key')
    readonly_fields = [field.name for field in UsageLog._meta.fields]

    def has_add_permission(self, request):
        return False

@admin.register(IntegrationKey)
class IntegrationKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'created_at', 'last_used_at')
    fields = ('name',)

    def get_readonly_fields(self, request, obj=None):
        return ('name', 'prefix', 'created_at', 'last_used_at') if obj else ()

    def get_fields(self, request, obj=None):
        return self.get_readonly_fields(request, obj) or self.fields

    def save_model(self, request, obj, form, change):
        if not change:
            # Kept on the instance only until the confirmation page shows it.
            obj._key = obj.generate()
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        """Show the key once, with the addresses Home Assistant needs.

        The key is rendered in this response only: it is not stored in a message,
        a cookie or the session.
        """
        base = request.build_absolute_uri('/').rstrip('/')
        modules = [(module, f"{base}{reverse('embed', args=[module])}#clave={obj._key}") for module in EMBED_MODULES]
        sensors = [(provider, f"{base}{reverse('ha-sensor', args=[provider])}") for provider in ('chatgpt', 'claude')]
        # The admin already marks this response no-store, so no copy of the key is cached.
        return TemplateResponse(request, 'admin/dashboard/integrationkey/created.html', {
            **self.admin_site.each_context(request), 'opts': self.opts, 'title': 'Clave creada',
            'record': obj, 'key': obj._key, 'modules': modules, 'sensors': sensors,
        })

from django.db import migrations, models


def unconnected_modes(apps, schema_editor):
    # The browser extension and the server's browser are gone: a provider that
    # used them has no source until it is connected again.
    ProviderStatus = apps.get_model('dashboard', 'ProviderStatus')
    ProviderStatus.objects.filter(collection_mode__in=('server', 'browser')).update(collection_mode='none')


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0007_providerstatus_client_auth_method'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='providerstatus',
            name='browser_refresh_requested_at',
        ),
        migrations.AlterField(
            model_name='providerstatus',
            name='collection_mode',
            field=models.CharField(choices=[('none', 'Sin conectar'), ('api', 'Cuenta conectada'), ('client', 'Cliente oficial en el servidor')], default='none', max_length=12),
        ),
        migrations.RunPython(unconnected_modes, migrations.RunPython.noop),
    ]

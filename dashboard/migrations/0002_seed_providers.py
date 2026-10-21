from django.db import migrations

def seed(apps, schema_editor):
    ProviderStatus = apps.get_model('dashboard', 'ProviderStatus')
    for provider in ('chatgpt', 'claude'):
        ProviderStatus.objects.using(schema_editor.connection.alias).get_or_create(provider=provider)

class Migration(migrations.Migration):
    dependencies = [('dashboard', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

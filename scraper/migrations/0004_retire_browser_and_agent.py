from django.db import migrations
from django.db.migrations.recorder import MigrationRecorder

# Tables of the retired «tokens» app (PC agent and token counters). The app no
# longer exists, so its own migrations cannot remove them.
TOKENS_TABLES = ('tokens_tokenusage', 'tokens_localsource', 'tokens_agentkey', 'tokens_logcursor')


def forget_retired_models(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    # Their permissions go with the content types.
    ContentType.objects.filter(app_label='tokens').delete()
    ContentType.objects.filter(app_label='scraper', model__in=('browsersynckey', 'scrapersession')).delete()
    MigrationRecorder(schema_editor.connection).migration_qs.filter(app='tokens').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('scraper', '0003_providercredential'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scrapersession',
            name='provider',
        ),
        migrations.DeleteModel(
            name='BrowserSyncKey',
        ),
        migrations.DeleteModel(
            name='ScraperSession',
        ),
        migrations.RunSQL([f'DROP TABLE IF EXISTS {table}' for table in TOKENS_TABLES], migrations.RunSQL.noop),
        migrations.RunPython(forget_retired_models, migrations.RunPython.noop),
    ]

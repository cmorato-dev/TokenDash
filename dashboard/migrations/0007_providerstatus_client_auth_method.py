from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0006_alter_providerstatus_collection_mode_client'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerstatus',
            name='client_auth_method',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='providerstatus',
            name='client_auth_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

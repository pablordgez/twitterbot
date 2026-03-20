from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_postingaccount_auth_mode_and_browser_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='postingaccountbrowsercredential',
            name='encrypted_storage_state',
            field=models.BinaryField(blank=True, null=True),
        ),
    ]

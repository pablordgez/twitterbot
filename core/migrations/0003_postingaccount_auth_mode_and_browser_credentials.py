from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_occurrence_resolved_tweet_entry_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='postingaccount',
            name='auth_mode',
            field=models.CharField(
                choices=[('request', 'Request Secrets'), ('browser', 'Browser Login')],
                default='request',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='PostingAccountBrowserCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('encrypted_username', models.BinaryField()),
                ('encrypted_password', models.BinaryField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='browser_credential', to='core.postingaccount')),
            ],
        ),
    ]

import pytest
import json
import hashlib
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from core.models.accounts import PostingAccount, PostingAccountSecret
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.history import HistoryEvent
from core.services.encryption import get_fernet_instance

User = get_user_model()

@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser('admin', 'admin@test.com', 'password')

@pytest.fixture
def logged_in_client(client, admin_user):
    client.login(username='admin', password='password')
    return client

@pytest.fixture
def account(db):
    return PostingAccount.objects.create(name="Test Account", is_active=True)

@pytest.fixture
def active_schedule(db):
    return Schedule.objects.create(
        schedule_type='one_time',
        start_datetime=timezone.now() + timedelta(days=1),
        content_mode='fixed_new',
        status='active'
    )

def test_account_list(logged_in_client, account):
    url = reverse('core:account_list')
    response = logged_in_client.get(url)
    assert response.status_code == 200
    assert "Test Account" in str(response.content)

def test_account_create(logged_in_client):
    url = reverse('core:account_create')
    response = logged_in_client.post(url, {
        'name': 'New Account',
        'is_active': True,
        'notification_mode': 'none'
    })
    assert response.status_code == 302
    assert PostingAccount.objects.filter(name='New Account').exists()

def test_account_update(logged_in_client, account):
    url = reverse('core:account_update', kwargs={'pk': account.pk})
    response = logged_in_client.post(url, {
        'name': 'Updated Name',
        'is_active': False,
        'notification_mode': 'every_failure'
    })
    assert response.status_code == 302
    account.refresh_from_db()
    assert account.name == 'Updated Name'
    assert not account.is_active

def test_account_detail_masked_secret(logged_in_client, account):
    # Create fake secret
    json_data = json.dumps({"test": "data"})
    f = get_fernet_instance()
    enc = f.encrypt(json_data.encode('utf-8'))
    fh = hashlib.sha256(json_data.encode('utf-8')).hexdigest()
    
    PostingAccountSecret.objects.create(account=account, encrypted_data=enc, field_hash=fh)
    
    url = reverse('core:account_detail', kwargs={'pk': account.pk})
    response = logged_in_client.get(url)
    assert response.status_code == 200
    # Should show masked version of the hash
    masked = f"••••••{fh[-4:]}"
    assert masked in response.content.decode('utf-8')
    assert "Credentials Configured" in str(response.content)

def test_account_delete_cascade_schedules(logged_in_client, account, active_schedule):
    ScheduleTargetAccount.objects.create(schedule=active_schedule, account=account)
    
    url = reverse('core:account_delete', kwargs={'pk': account.pk})
    # GET shows warnings
    response = logged_in_client.get(url)
    assert response.status_code == 200
    assert "Warning: Dependency Impact" in str(response.content)
    
    # POST deletes and cascades
    response = logged_in_client.post(url)
    assert response.status_code == 302
    assert not PostingAccount.objects.filter(id=account.id).exists()
    
    active_schedule.refresh_from_db()
    assert active_schedule.status == 'canceled'

def test_curl_import_valid(logged_in_client, account):
    curl_input = """
    curl 'https://x.com/i/api/graphql/TEST_QID/CreateTweet' -H 'authorization: Bearer A' -H 'x-csrf-token: B' -b 'auth_token=C; ct0=D; twid=E'
    """
    url = reverse('core:account_import', kwargs={'pk': account.pk})
    response = logged_in_client.post(url, {'curl_text': curl_input})
    assert response.status_code == 302
    
    account.refresh_from_db()
    assert hasattr(account, 'secret')
    
    event = HistoryEvent.objects.filter(account=account).first()
    assert event is not None
    assert event.event_type == 'ACCOUNT_IMPORT_ACCEPTED'

def test_test_post_requires_csrf_post(logged_in_client, account):
    url = reverse('core:account_test_post', kwargs={'pk': account.pk})
    # GET should fail because view only has def post
    response = logged_in_client.get(url)
    assert response.status_code == 405 # Method Not Allowed
    
    response = logged_in_client.post(url)
    assert response.status_code == 302
    assert HistoryEvent.objects.filter(event_type='TEST_POST_CONFIRMED').exists()

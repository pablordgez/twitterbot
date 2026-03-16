import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.accounts import PostingAccount
from core.models.execution import Occurrence
from core.models.history import HistoryEvent

@pytest.fixture
def test_account(db):
    return PostingAccount.objects.create(
        name="Test Account",
        handle="testacc"
    )

@pytest.fixture
def one_time_schedule(db, test_account):
    now = timezone.now()
    schedule = Schedule.objects.create(
        name="Past Test Schedule",
        schedule_type=Schedule.ScheduleType.ONE_TIME,
        start_datetime=now - timedelta(days=2),
        timezone_name="UTC",
        content_mode=Schedule.ContentMode.FIXED_NEW,
        fixed_content="Past text",
        status="active",
        version=1
    )
    ScheduleTargetAccount.objects.create(schedule=schedule, account=test_account)
    return schedule

@pytest.fixture
def past_occurrence(db, one_time_schedule):
    return Occurrence.objects.create(
        schedule=one_time_schedule,
        due_at=one_time_schedule.start_datetime,
        display_timezone="UTC",
        schedule_version=1,
        status=Occurrence.Status.COMPLETED
    )

@pytest.mark.django_db
def test_schedule_edit_preserves_past_occurrence(client, django_user_model, one_time_schedule, past_occurrence, test_account):
    user = django_user_model.objects.create_user(username='admin', password='password')
    client.login(username='admin', password='password')

    url = reverse('core:schedule_edit', kwargs={'pk': one_time_schedule.pk})

    # Prepare edit payload (future start_datetime)
    future_date = timezone.now() + timedelta(days=1)
    data = {
        'name': 'Updated Schedule',
        'schedule_type': Schedule.ScheduleType.ONE_TIME,
        'start_datetime': future_date.strftime('%Y-%m-%dT%H:%M:%S'),
        'timezone_mode': 'utc',
        'content_mode': Schedule.ContentMode.FIXED_NEW,
        'fixed_content': 'New text',
        'target_accounts': [test_account.pk]
    }

    response = client.post(url, data)
    assert response.status_code == 302

    # Check that past occurrence is still completed
    past_occurrence.refresh_from_db()
    assert past_occurrence.status == Occurrence.Status.COMPLETED

    # Check that a new pending occurrence was generated
    new_occurrences = Occurrence.objects.filter(
        schedule=one_time_schedule, 
        status=Occurrence.Status.PENDING
    )
    assert new_occurrences.exists()
    assert new_occurrences.first().due_at == future_date.replace(microsecond=0)

    # Check version incremented
    one_time_schedule.refresh_from_db()
    assert one_time_schedule.version == 2
    assert one_time_schedule.name == 'Updated Schedule'

    # Check history event
    event = HistoryEvent.objects.filter(schedule=one_time_schedule, event_type='SCHEDULE_EDITED').exists()
    assert event

@pytest.mark.django_db
def test_schedule_edit_regenerates_future_recurring(client, django_user_model, test_account):
    user = django_user_model.objects.create_user(username='admin', password='password')
    client.login(username='admin', password='password')

    now = timezone.now()
    schedule = Schedule.objects.create(
        name="Recurring Schedule",
        schedule_type=Schedule.ScheduleType.RECURRING,
        start_datetime=now + timedelta(days=1),
        timezone_name="America/New_York",
        content_mode=Schedule.ContentMode.FIXED_NEW,
        fixed_content="Loop text",
        interval_type=Schedule.IntervalType.DAYS,
        interval_value=1,
        status="active",
        version=1
    )
    ScheduleTargetAccount.objects.create(schedule=schedule, account=test_account)
    
    from core.services.occurrence_materializer import materialize_for_schedule
    materialize_for_schedule(schedule)

    # Count initial occurrences
    initial_count = Occurrence.objects.filter(schedule=schedule).count()

    # Edit the recurrence interval to 2 days
    url = reverse('core:schedule_edit', kwargs={'pk': schedule.pk})
    data = {
        'name': 'Updated Recurring',
        'schedule_type': Schedule.ScheduleType.RECURRING,
        'start_datetime': (now + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S'),
        'timezone_mode': 'other',
        'timezone_other': 'America/New_York',
        'content_mode': Schedule.ContentMode.FIXED_NEW,
        'fixed_content': 'Loop text',
        'interval_type': Schedule.IntervalType.DAYS,
        'interval_value': 2,
        'target_accounts': [test_account.pk]
    }

    response = client.post(url, data)
    assert response.status_code == 302

    schedule.refresh_from_db()
    assert schedule.version == 2
    assert schedule.interval_value == 2

    # Should have fewer occurrences with an interval of 2 days vs 1 day
    new_count = Occurrence.objects.filter(schedule=schedule).count()
    assert new_count < initial_count

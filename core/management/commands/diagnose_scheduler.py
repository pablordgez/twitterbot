from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Min
from django.utils import timezone

from core.models.execution import Occurrence, RecurringUsageState
from core.models.history import HistoryEvent
from core.models.schedules import Schedule
from core.models.system import SchedulerLease
from core.models.tweets import TweetEntry


class Command(BaseCommand):
    help = 'Print non-secret scheduler, occurrence, and schedule diagnostics.'

    def handle(self, *args, **options):
        now = timezone.now()

        self.stdout.write("Scheduler diagnostics")
        self.stdout.write(f"Now: {now.isoformat()}")
        self.stdout.write(f"Database: {settings.DATABASES['default']['NAME']}")
        self.stdout.write("")

        self._write_lease(now)
        self._write_occurrence_summary(now)
        self._write_history_summary()
        self._write_active_schedule_summary(now)

    def _write_lease(self, now):
        self.stdout.write("Lease")
        leases = list(SchedulerLease.objects.order_by('id'))
        if not leases:
            self.stdout.write("  No scheduler lease row exists.")
            self.stdout.write("")
            return

        for lease in leases:
            age_seconds = (now - lease.renewed_at).total_seconds()
            active_by_time = lease.is_active and age_seconds <= 30
            self.stdout.write(
                "  "
                f"id={lease.id} owner={lease.owner_id} active={lease.is_active} "
                f"renewed_at={lease.renewed_at.isoformat()} age_seconds={age_seconds:.0f} "
                f"current={active_by_time}"
            )
        self.stdout.write("")

    def _write_occurrence_summary(self, now):
        self.stdout.write("Occurrences")
        rows = (
            Occurrence.objects.values('status')
            .annotate(count=Count('id'), oldest_due=Min('due_at'))
            .order_by('status')
        )
        for row in rows:
            oldest_due = row['oldest_due'].isoformat() if row['oldest_due'] else 'n/a'
            self.stdout.write(
                f"  status={row['status']} count={row['count']} oldest_due={oldest_due}"
            )

        pending = Occurrence.objects.filter(status=Occurrence.Status.PENDING)
        due_pending = pending.filter(due_at__lte=now)
        future_pending = pending.filter(due_at__gt=now)
        executing_stale = Occurrence.objects.filter(
            status=Occurrence.Status.EXECUTING,
            updated_at__lt=now - timedelta(minutes=5),
        )

        self.stdout.write(f"  due_pending_now={due_pending.count()}")
        self.stdout.write(f"  future_pending={future_pending.count()}")
        self.stdout.write(f"  stale_executing_older_than_5m={executing_stale.count()}")

        oldest_due = due_pending.order_by('due_at').first()
        next_future = future_pending.order_by('due_at').first()
        if oldest_due:
            self.stdout.write(
                f"  oldest_due_pending=id:{oldest_due.id} schedule:{oldest_due.schedule_id} "
                f"due_at:{oldest_due.due_at.isoformat()}"
            )
        if next_future:
            self.stdout.write(
                f"  next_future_pending=id:{next_future.id} schedule:{next_future.schedule_id} "
                f"due_at:{next_future.due_at.isoformat()}"
            )
        self.stdout.write("")

    def _write_history_summary(self):
        self.stdout.write("History")
        latest = HistoryEvent.objects.order_by('-timestamp').first()
        latest_scheduled = (
            HistoryEvent.objects.filter(
                event_type__in=[
                    'OCCURRENCE_CLAIMED',
                    'OCCURRENCE_MISSED',
                    'OCCURRENCE_EXECUTION_BLOCKED',
                    'POST_ATTEMPT_SUCCEEDED',
                    'POST_ATTEMPT_FAILED',
                ]
            )
            .order_by('-timestamp')
            .first()
        )

        if latest:
            self.stdout.write(
                f"  latest=id:{latest.id} at:{latest.timestamp.isoformat()} type:{latest.event_type}"
            )
        else:
            self.stdout.write("  No history rows exist.")

        if latest_scheduled:
            self.stdout.write(
                "  "
                f"latest_scheduled=id:{latest_scheduled.id} "
                f"at:{latest_scheduled.timestamp.isoformat()} "
                f"type:{latest_scheduled.event_type}"
            )
        else:
            self.stdout.write("  No scheduled-post history rows exist.")
        self.stdout.write("")

    def _write_active_schedule_summary(self, now):
        self.stdout.write("Active schedules")
        schedules = Schedule.objects.filter(status='active').order_by('id')
        if not schedules.exists():
            self.stdout.write("  No active schedules.")
            self.stdout.write("")
            return

        for schedule in schedules:
            pending = schedule.occurrences.filter(status=Occurrence.Status.PENDING)
            next_pending = pending.filter(due_at__gt=now).order_by('due_at').first()
            overdue_count = pending.filter(due_at__lte=now).count()
            target_count = schedule.target_accounts.count()
            source_list_ids = list(schedule.source_lists.values_list('tweet_list_id', flat=True))
            source_list_count = len(source_list_ids)
            next_due = next_pending.due_at.isoformat() if next_pending else 'none'

            self.stdout.write(
                "  "
                f"id={schedule.id} type={schedule.schedule_type} mode={schedule.content_mode} "
                f"targets={target_count} source_lists={source_list_count} "
                f"pending_overdue={overdue_count} next_future={next_due}"
            )

            if (
                schedule.schedule_type == Schedule.ScheduleType.RECURRING
                and schedule.content_mode
                in [Schedule.ContentMode.RANDOM_FROM_LIST, Schedule.ContentMode.RANDOM_FROM_LISTS]
                and not schedule.reuse_enabled
            ):
                total_entries = TweetEntry.objects.filter(list_id__in=source_list_ids).count()
                used_entries = RecurringUsageState.objects.filter(schedule=schedule).count()
                remaining = max(total_entries - used_entries, 0)
                self.stdout.write(
                    "    "
                    f"random_pool total_entries={total_entries} used={used_entries} "
                    f"remaining_before_reset={remaining} exhaustion={schedule.exhaustion_behavior}"
                )
        self.stdout.write("")

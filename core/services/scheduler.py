import logging
import time
from datetime import timedelta
from django.utils import timezone
from django.db import transaction, IntegrityError

from core.models.system import SchedulerLease
from core.models.execution import Occurrence, OccurrenceAttempt
from core.services.history import log_event
from core.services.occurrence_materializer import refresh_rolling_horizon
from core.services.posting_executor import execute_occurrence_attempts

logger = logging.getLogger(__name__)

LEASE_DURATION_SECONDS = 30
GRACE_PERIOD_MINUTES = 1

def acquire_or_renew_lease(owner_id: str) -> bool:
    now = timezone.now()
    with transaction.atomic():
        lease = SchedulerLease.objects.select_for_update().first()
        if not lease:
            SchedulerLease.objects.create(owner_id=owner_id, is_active=True)
            return True

        if lease.owner_id == owner_id:
            lease.renewed_at = now
            lease.is_active = True
            lease.save()
            return True

        expiration_time = lease.renewed_at + timedelta(seconds=LEASE_DURATION_SECONDS)
        if now > expiration_time or not lease.is_active:
            lease.owner_id = owner_id
            lease.renewed_at = now
            lease.is_active = True
            lease.save()
            return True

    return False

def startup_scan_missed() -> int:
    now = timezone.now()
    cutoff = now - timedelta(minutes=GRACE_PERIOD_MINUTES)

    missed_occurrences = Occurrence.objects.filter(
        status=Occurrence.Status.PENDING,
        due_at__lt=cutoff
    )

    count = 0
    for occ in missed_occurrences:
        occ.status = Occurrence.Status.MISSED
        occ.save()
        count += 1
        log_event(
            event_type='OCCURRENCE_MISSED',
            schedule=occ.schedule,
            occurrence=occ,
            detail={'reason': f'Missed due to being past grace period of {GRACE_PERIOD_MINUTES}m'}
        )
    return count

def execute_scheduler_tick(owner_id: str) -> bool:
    if not acquire_or_renew_lease(owner_id):
        logger.warning(f"SCHEDULER_LEASE_CONFLICT: {owner_id} failed to acquire lease")
        log_event('SCHEDULER_LEASE_CONFLICT', detail={'owner_id': owner_id})
        return False

    now = timezone.now()
    due_occurrences = list(Occurrence.objects.filter(
        status=Occurrence.Status.PENDING,
        due_at__lte=now
    ))

    for occ in due_occurrences:
        try:
            with transaction.atomic():
                occ_locked = Occurrence.objects.select_for_update(nowait=True).get(id=occ.id)
                if occ_locked.status != Occurrence.Status.PENDING:
                    continue

                occ_locked.status = Occurrence.Status.EXECUTING
                occ_locked.save()

                targets = occ_locked.schedule.target_accounts.all()
                for target in targets:
                    OccurrenceAttempt.objects.create(
                        occurrence=occ_locked,
                        target_account=target.account,
                        automatic_attempt_seq=1,
                        validation_ok=False
                    )

                log_event(
                    event_type='OCCURRENCE_CLAIMED',
                    schedule=occ_locked.schedule,
                    occurrence=occ_locked,
                    detail={'accounts_count': targets.count()}
                )
        except IntegrityError:
            logger.warning(f"Occurrence {occ.id} targets unique constraint failed during claim.")
            continue
        except Exception as e:
            logger.error(f"Error claiming occurrence {occ.id}: {e}")
            continue

        # Dispatch to posting executor
        # We catch exceptions here to avoid failing the whole tick if one dispatch fails
        try:
            execute_occurrence_attempts(occ.id)
        except Exception as e:
            logger.error(f"Error executing occurrence {occ.id}: {e}")
            # If standard executor is broken, we should mark failure manually
            occ.status = Occurrence.Status.FAILED
            occ.save()

    try:
        refresh_rolling_horizon()
    except Exception as e:
        logger.error(f"Error refreshing rolling horizon: {e}")

    return True

def run_scheduler_loop(owner_id: str, stop_event=None):
    logger.info(f"Starting scheduler loop with owner {owner_id}")
    log_event('SCHEDULER_LEASE_ACQUIRED', detail={'owner_id': owner_id})
    startup_scan_missed()

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            execute_scheduler_tick(owner_id)
        except Exception as e:
            logger.error(f"Scheduler tick error: {e}")

        if stop_event and stop_event.wait(10):
            break
        elif not stop_event:
            time.sleep(10)

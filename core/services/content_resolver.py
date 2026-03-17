import random
from typing import Optional, Tuple
from django.db import transaction
from core.models.execution import Occurrence, RecurringUsageState
from core.models.schedules import Schedule
from core.models.tweets import TweetEntry
from core.services.history import log_event

def resolve_content_for_occurrence(occurrence: Occurrence):
    """
    Resolves content for a given occurrence based on its schedule's configuration.
    Updates the occurrence and its associated attempts with the resolved content.
    """
    schedule = occurrence.schedule
    attempts = occurrence.attempts.all()

    def get_content_choice() -> Tuple[Optional[str], Optional[TweetEntry]]:
        if schedule.content_mode in [Schedule.ContentMode.FIXED_NEW, Schedule.ContentMode.FIXED_FROM_LIST]:
            return schedule.fixed_content, None
            
        elif schedule.content_mode in [Schedule.ContentMode.RANDOM_FROM_LIST, Schedule.ContentMode.RANDOM_FROM_LISTS]:
            source_lists = schedule.source_lists.all()
            if not source_lists:
                return None, None
            list_ids = [sl.tweet_list_id for sl in source_lists]
            
            entries = TweetEntry.objects.filter(list_id__in=list_ids)
            
            if not schedule.reuse_enabled and schedule.schedule_type == Schedule.ScheduleType.RECURRING:
                used_entry_ids = RecurringUsageState.objects.filter(schedule=schedule).values_list('tweet_entry_id', flat=True)
                entries = entries.exclude(id__in=used_entry_ids)
                
                if not entries.exists():
                    if schedule.exhaustion_behavior == Schedule.ExhaustionBehavior.RESET:
                        RecurringUsageState.objects.filter(schedule=schedule).delete()
                        # Refetch entries after reset
                        entries = TweetEntry.objects.filter(list_id__in=list_ids)
                        if not entries.exists():
                            return None, None
                    elif schedule.exhaustion_behavior == Schedule.ExhaustionBehavior.SKIP:
                        return "EXHAUSTED_SKIP", None
                    elif schedule.exhaustion_behavior == Schedule.ExhaustionBehavior.STOP:
                        return "EXHAUSTED_STOP", None

            if entries.exists():
                entry_list = list(entries)
                chosen = random.choice(entry_list)
                return chosen.text, chosen
            return None, None
        return "", None

    is_shared = (
        schedule.content_mode in [Schedule.ContentMode.FIXED_NEW, Schedule.ContentMode.FIXED_FROM_LIST] or
        schedule.random_resolution_mode == Schedule.RandomResolutionMode.SHARED
    )

    with transaction.atomic():
        if is_shared:
            content, tweet_entry = get_content_choice()
            
            if content in ["EXHAUSTED_SKIP", "EXHAUSTED_STOP"]:
                _handle_exhaustion(occurrence, content)
                return

            occurrence.content_resolved = True
            occurrence.resolved_content = content
            occurrence.resolved_tweet_entry = tweet_entry
            occurrence.save(update_fields=['resolved_content', 'resolved_tweet_entry', 'content_resolved'])
            for attempt in attempts:
                attempt.resolved_content = content
                attempt.resolved_tweet_entry = tweet_entry
                attempt.save(update_fields=['resolved_content', 'resolved_tweet_entry'])
        else:
            # PER_ACCOUNT resolution
            occurrence.content_resolved = True
            occurrence.resolved_content = None # Not shared
            occurrence.resolved_tweet_entry = None
            occurrence.save(update_fields=['resolved_content', 'resolved_tweet_entry', 'content_resolved'])
            for attempt in attempts:
                content, tweet_entry = get_content_choice()
                
                if content in ["EXHAUSTED_SKIP", "EXHAUSTED_STOP"]:
                    _handle_exhaustion(occurrence, content)
                    return
                
                attempt.resolved_content = content
                attempt.resolved_tweet_entry = tweet_entry
                attempt.save(update_fields=['resolved_content', 'resolved_tweet_entry'])

def _handle_exhaustion(occurrence: Occurrence, exhaust_type: str):
    schedule = occurrence.schedule
    occurrence.status = Occurrence.Status.SKIPPED
    if exhaust_type == "EXHAUSTED_SKIP":
        reason = "all tweets exhausted – skip until more added"
    else:
        reason = "all tweets exhausted – stop"
    log_event(
        event_type='OCCURRENCE_EXECUTION_BLOCKED',
        schedule=schedule,
        occurrence=occurrence,
        content_summary=reason,
        result_status=Occurrence.Status.SKIPPED,
        detail={'reason': reason},
        correlation_id=f"occurrence:{occurrence.id}",
    )
    occurrence.cancel_reason = reason
    occurrence.save(update_fields=['status', 'cancel_reason'])

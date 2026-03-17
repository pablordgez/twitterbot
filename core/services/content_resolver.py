import random
from typing import Optional
from django.db import transaction
from core.models.execution import Occurrence
from core.models.schedules import Schedule
from core.models.tweets import TweetEntry

def resolve_content_for_occurrence(occurrence: Occurrence):
    """
    Resolves content for a given occurrence based on its schedule's configuration.
    Updates the occurrence and its associated attempts with the resolved content.
    """
    schedule = occurrence.schedule
    attempts = occurrence.attempts.all()

    def get_content_choice() -> Optional[str]:
        if schedule.content_mode in [Schedule.ContentMode.FIXED_NEW, Schedule.ContentMode.FIXED_FROM_LIST]:
            return schedule.fixed_content
            
        elif schedule.content_mode in [Schedule.ContentMode.RANDOM_FROM_LIST, Schedule.ContentMode.RANDOM_FROM_LISTS]:
            source_lists = schedule.source_lists.all()
            if not source_lists:
                return None
            list_ids = [sl.tweet_list_id for sl in source_lists]
            
            entries = TweetEntry.objects.filter(list_id__in=list_ids)
            if entries.exists():
                entry_list = list(entries)
                return random.choice(entry_list).text
            return None
        return ""

    is_shared = (
        schedule.content_mode in [Schedule.ContentMode.FIXED_NEW, Schedule.ContentMode.FIXED_FROM_LIST] or
        schedule.random_resolution_mode == Schedule.RandomResolutionMode.SHARED
    )

    with transaction.atomic():
        occurrence.content_resolved = True
        
        if is_shared:
            content = get_content_choice()
            occurrence.resolved_content = content
            occurrence.save(update_fields=['resolved_content', 'content_resolved'])
            for attempt in attempts:
                attempt.resolved_content = content
                attempt.save(update_fields=['resolved_content'])
        else:
            # PER_ACCOUNT resolution
            occurrence.resolved_content = None # Not shared
            occurrence.save(update_fields=['resolved_content', 'content_resolved'])
            for attempt in attempts:
                attempt.resolved_content = get_content_choice()
                attempt.save(update_fields=['resolved_content'])

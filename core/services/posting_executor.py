def execute_posting_attempt(attempt_id: int) -> None:
    """
    Mock dispatcher for T-019. 
    Actual implementation will be in T-020.
    """
    from core.models.execution import OccurrenceAttempt
    attempt = OccurrenceAttempt.objects.get(id=attempt_id)
    attempt.post_result = OccurrenceAttempt.PostResult.SUCCESS
    attempt.validation_ok = True
    attempt.save()

def execute_occurrence_attempts(occurrence_id: int) -> None:
    from core.models.execution import Occurrence, OccurrenceAttempt
    occ = Occurrence.objects.get(id=occurrence_id)
    attempts = OccurrenceAttempt.objects.filter(occurrence=occ)
    
    for attempt in attempts:
        execute_posting_attempt(attempt.id)
        
    # Check if all completed successfully
    all_success = True
    for attempt in attempts:
        attempt.refresh_from_db()
        if attempt.post_result != OccurrenceAttempt.PostResult.SUCCESS:
            all_success = False
            
    if all_success:
        occ.status = Occurrence.Status.COMPLETED
    else:
        occ.status = Occurrence.Status.FAILED
    occ.save()

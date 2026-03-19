import json
import logging
import requests

from core.models.accounts import PostingAccount
from core.models.execution import OccurrenceAttempt, Occurrence, RecurringUsageState
from core.models.schedules import Schedule
from core.services.encryption import decrypt
from core.services.history import log_event, redact_secrets
from core.services.content_resolver import resolve_content_for_occurrence
from core.services.notification_engine import handle_posting_result

logger = logging.getLogger(__name__)

HARDCODED_HEADERS = {
    'content-type': 'application/json',
    'origin': 'https://x.com',
    'referer': 'https://x.com/compose/post'
}

FEATURES_PAYLOAD = {
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False
}


def _attempt_correlation_id(attempt: OccurrenceAttempt) -> str:
    return f"occurrence:{attempt.occurrence_id}:account:{attempt.target_account_id}"


def _truncate_log_value(value, *, limit=1000):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _log_create_tweet_response(status_code: int, data, *, success: bool, error_detail: str = ""):
    sanitized_body = _truncate_log_value(redact_secrets(data))
    if success:
        logger.info("CreateTweet succeeded: status=%s body=%s", status_code, sanitized_body)
    else:
        logger.warning(
            "CreateTweet failed: status=%s error=%s body=%s",
            status_code,
            _truncate_log_value(_redact_error(error_detail), limit=300),
            sanitized_body,
        )

def execute_occurrence_attempts(occurrence_id: int):
    """
    Executes all attempts for a given occurrence.
    Resolves content before executing attempts.
    """
    try:
        occurrence = Occurrence.objects.get(id=occurrence_id)
    except Occurrence.DoesNotExist:
        logger.error(f"Occurrence {occurrence_id} not found.")
        return

    # Resolve content
    if not occurrence.content_resolved:
        resolve_content_for_occurrence(occurrence)

    # Execute attempts
    attempts = occurrence.attempts.all()
    all_success = True
    any_success = False

    for attempt in attempts:
        try:
            execute_attempt(attempt)
            attempt.refresh_from_db()
            if attempt.post_result == OccurrenceAttempt.PostResult.SUCCESS:
                any_success = True
            else:
                all_success = False
        except Exception as e:
            logger.error(f"Error executing attempt {attempt.id}: {e}")
            all_success = False

    # Finalize status
    if all_success and attempts.exists():
        occurrence.status = Occurrence.Status.COMPLETED
    elif any_success:
        occurrence.status = Occurrence.Status.COMPLETED
    else:
        occurrence.status = Occurrence.Status.FAILED

    occurrence.save(update_fields=['status'])

def execute_attempt(attempt: OccurrenceAttempt):
    """
    Executes a posting attempt for an occurrence against X.com.
    """
    account = attempt.target_account
    content = attempt.resolved_content or ""
    occurrence = attempt.occurrence

    # Pre-validation
    if not account.is_active:
        _fail_attempt(attempt, "validation_failed", "Account is inactive")
        return

    if occurrence.status == Occurrence.Status.CANCELED or occurrence.schedule.status == 'canceled':
        _fail_attempt(attempt, "validation_failed", "Schedule or occurrence is canceled")
        return

    if not content or len(content) > 280:
        _fail_attempt(attempt, "validation_failed", "Tweet length invalid")
        return

    if not hasattr(account, 'secret'):
        _fail_attempt(attempt, "validation_failed", "Account missing secrets")
        return

    try:
        decrypted_json = decrypt(account.secret.encrypted_data)
        secret_data = json.loads(decrypted_json)
    except Exception:
        _fail_attempt(attempt, "validation_failed", "Secrets decryptable check failed")
        return

    # Validation passed
    attempt.validation_ok = True
    attempt.save(update_fields=['validation_ok'])

    success, error_detail, response_meta = _execute_post(content, secret_data)

    if success:
        attempt.post_result = OccurrenceAttempt.PostResult.SUCCESS
        attempt.external_response_meta = response_meta
        attempt.save(update_fields=['post_result', 'external_response_meta'])

        if occurrence.schedule.schedule_type == Schedule.ScheduleType.RECURRING and not occurrence.schedule.reuse_enabled:
            if attempt.resolved_tweet_entry_id:
                RecurringUsageState.objects.get_or_create(
                    schedule=occurrence.schedule,
                    tweet_entry_id=attempt.resolved_tweet_entry_id
                )

        log_event(
            event_type='POST_ATTEMPT_SUCCEEDED',
            account=account,
            schedule=occurrence.schedule,
            occurrence=occurrence,
            content_summary=attempt.resolved_content or "",
            result_status=OccurrenceAttempt.PostResult.SUCCESS,
            correlation_id=_attempt_correlation_id(attempt),
        )
        handle_posting_result(account, True, attempt)
    else:
        attempt.post_result = OccurrenceAttempt.PostResult.FAILED
        attempt.error_detail = _redact_error(error_detail)
        attempt.save(update_fields=['post_result', 'error_detail'])

        log_event(
            event_type='POST_ATTEMPT_FAILED',
            account=account,
            schedule=occurrence.schedule,
            occurrence=occurrence,
            content_summary=attempt.resolved_content or "",
            result_status=OccurrenceAttempt.PostResult.FAILED,
            detail={'error': attempt.error_detail},
            correlation_id=_attempt_correlation_id(attempt),
        )
        handle_posting_result(account, False, attempt)

def execute_test_post(account: PostingAccount, content: str = 'test') -> tuple[bool, str]:
    """
    Executes a test post bypassing database occurrence records.
    Returns (success, error_detail).
    """
    if not account.is_active:
        return False, "Account is inactive"

    if not content or len(content) > 280:
        return False, "Tweet length invalid"

    if not hasattr(account, 'secret'):
        return False, "Account missing secrets"

    try:
        decrypted_json = decrypt(account.secret.encrypted_data)
        secret_data = json.loads(decrypted_json)
    except Exception:
        return False, "Secrets decryptable check failed"

    success, error_detail, _ = _execute_post(content, secret_data)

    if not success:
        error_detail = _redact_error(error_detail)

    return success, error_detail

def _execute_post(content: str, secret_data: dict) -> tuple[bool, str, dict]:
    """
    Performs the HTTP request.
    Returns (success, error_detail, response_meta)
    """
    query_id = secret_data.get('queryId')
    headers = secret_data.get('headers', {})
    cookies = secret_data.get('cookies', {})

    if not query_id:
        return False, "Missing queryId in secrets", {}

    url = f"https://x.com/i/api/graphql/{query_id}/CreateTweet"

    # Merge hardcoded headers into secret headers
    merged_headers = {**headers, **HARDCODED_HEADERS}

    payload = {
        "variables": {
            "tweet_text": content,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False
            },
            "dark_request": False,
            "withDownvotePerspective": False,
            "withArticleRichContentState": False,
            "withSuperFollowsUserFields": True,
            "withSuperFollowsTweetFields": True,
            "semantic_annotation_ids": []
        },
        "features": FEATURES_PAYLOAD,
        "queryId": query_id
    }

    try:
        response = requests.post(
            url,
            headers=merged_headers,
            cookies=cookies,
            json=payload,
            verify=True,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()

        success, error_detail = _interpret_create_tweet_response(data)
        if not success:
            _log_create_tweet_response(response.status_code, data, success=False, error_detail=error_detail)
            return False, error_detail, {"status_code": response.status_code}

        _log_create_tweet_response(response.status_code, data, success=True)
        return True, "", {"status_code": response.status_code}

    except requests.exceptions.RequestException as e:
        logger.warning("CreateTweet request exception: %s", _truncate_log_value(_redact_error(str(e)), limit=300))
        return False, str(e), {}
    except ValueError: # JSON decode error
        logger.warning("CreateTweet failed: status=%s invalid_json_response", response.status_code)
        return False, "Invalid JSON response from server format", {}

def _fail_attempt(attempt: OccurrenceAttempt, result: str, detail: str):
    attempt.post_result = result
    attempt.validation_ok = False
    attempt.error_detail = detail
    attempt.save(update_fields=['post_result', 'validation_ok', 'error_detail'])

    log_event(
        event_type='POST_ATTEMPT_FAILED',
        account=attempt.target_account,
        schedule=attempt.occurrence.schedule,
        occurrence=attempt.occurrence,
        content_summary=attempt.resolved_content or "",
        result_status=result,
        detail={'error': detail},
        correlation_id=_attempt_correlation_id(attempt),
    )
    handle_posting_result(attempt.target_account, False, attempt)

def _redact_error(error_str: str) -> str:
    """
    Strip any URL parameters or secret-looking values from error details.
    Mainly needed to ensure no headers or tokens leaked.
    """
    if not error_str:
        return ""

    # Redact potential keys (like bearer token, csrf, auth_token, queryId)
    # Simple redaction logic: truncate excessively long string segments
    # and remove the common host string partially just in case, though
    # the requirements say "Strip any secrets from error details before storage".
    # Typically requests.exceptions includes the URL.
    import re
    # Redact queryId or tokens in URL if it leaked in exception
    error_str = re.sub(r'/graphql/[A-Za-z0-9_-]+/CreateTweet', '/graphql/[REDACTED]/CreateTweet', error_str)
    # Redact anything looking like a token (long unspaced alphanumeric)
    # But be careful not to redact normal error words.
    # tokens are usually >= 32 chars
    error_str = re.sub(r'\b[A-Za-z0-9_-]{32,}\b', '[REDACTED]', error_str)

    return error_str


def _interpret_create_tweet_response(data: dict) -> tuple[bool, str]:
    """
    X can return HTTP 200 while still rejecting the mutation at the GraphQL layer.
    Treat the response as success only when it contains a concrete tweet identifier.
    """
    if not isinstance(data, dict):
        return False, "Unexpected response format from server"

    errors = data.get('errors')
    if isinstance(errors, list) and errors:
        err_msgs = [e.get('message', 'Unknown GraphQL Error') for e in errors if isinstance(e, dict)]
        return False, f"GraphQL Error: {', '.join(err_msgs) or 'Unknown GraphQL Error'}"

    result = (
        data.get('data', {})
        .get('create_tweet', {})
        .get('tweet_results', {})
        .get('result', {})
    )

    if not isinstance(result, dict):
        return False, "CreateTweet response missing result payload"

    rest_id = result.get('rest_id')
    legacy_id = result.get('legacy', {}).get('id_str') if isinstance(result.get('legacy'), dict) else None
    typename = result.get('__typename')

    if rest_id or legacy_id:
        return True, ""

    if typename:
        return False, f"CreateTweet returned {typename} without a tweet id"

    return False, "CreateTweet response missing tweet id"

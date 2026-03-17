import re
from collections.abc import Sequence

from core.models.history import HistoryEvent

REDACTION_PLACEHOLDER = '***REDACTED***'
SENSITIVE_KEY_PARTS = {
    'api_key',
    'auth',
    'authorization',
    'bearer',
    'cookie',
    'csrf',
    'password',
    'queryid',
    'secret',
    'token',
}
STRING_REDACTION_PATTERNS = (
    re.compile(r'(?i)(authorization)(\s*[:=]\s*)(bearer\s+)([^,\s;]+)'),
    re.compile(r'(?i)(authorization|bearer|token|auth_token|ct0|csrf(?:_token)?|api[_-]?key|password|secret|queryid)(\s*[:=]\s*)([^,\s;]+)'),
    re.compile(r'/graphql/[A-Za-z0-9_-]+/CreateTweet'),
    re.compile(r'\b[A-Za-z0-9_+/=-]{32,}\b'),
)


def _is_sensitive_key(key):
    key_lower = str(key).lower()
    return any(part in key_lower for part in SENSITIVE_KEY_PARTS)


def _redact_string(value):
    redacted = value
    redacted = STRING_REDACTION_PATTERNS[0].sub(r'\1\2\3' + REDACTION_PLACEHOLDER, redacted)
    redacted = STRING_REDACTION_PATTERNS[1].sub(r'\1\2' + REDACTION_PLACEHOLDER, redacted)
    redacted = STRING_REDACTION_PATTERNS[2].sub('/graphql/[REDACTED]/CreateTweet', redacted)
    redacted = STRING_REDACTION_PATTERNS[3].sub('[REDACTED]', redacted)
    return redacted


def _summarize_random_content(schedule):
    if not schedule:
        return ""

    if schedule.content_mode not in {'random_from_list', 'random_from_lists'}:
        return ""

    source_names = list(
        schedule.source_lists.select_related('tweet_list').values_list('tweet_list__name', flat=True)
    )
    if len(source_names) == 1:
        return f"Random from {source_names[0]}"
    if len(source_names) > 1:
        return f"Random from {len(source_names)} lists"
    return "Random content"


def redact_secrets(data, key_name=None):
    """
    Recursively remove or mask sensitive fields before saving to history.
    """
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTION_PLACEHOLDER
            else:
                redacted[key] = redact_secrets(value, key_name=key)
        return redacted

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return [redact_secrets(item, key_name=key_name) for item in data]

    if isinstance(data, str):
        if key_name and _is_sensitive_key(key_name):
            return REDACTION_PLACEHOLDER
        return _redact_string(data)

    return data


def truncate_content_summary(text):
    if not text:
        return ""
    if len(text) > 100:
        return text[:97] + "..."
    return text


def log_event(
    event_type,
    *,
    account=None,
    schedule=None,
    occurrence=None,
    content_summary='',
    result_status='',
    detail=None,
    correlation_id=''
):
    """
    Creates a HistoryEvent.
    """
    if detail is not None:
        detail = redact_secrets(detail)

    if not content_summary:
        content_summary = _summarize_random_content(schedule or getattr(occurrence, 'schedule', None))

    return HistoryEvent.objects.create(
        event_type=event_type,
        account=account,
        schedule=schedule,
        occurrence=occurrence,
        content_summary=truncate_content_summary(content_summary),
        result_status=result_status,
        detail=detail,
        correlation_id=correlation_id or ''
    )

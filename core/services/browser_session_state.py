import json
from urllib.parse import urlparse


class BrowserSessionStateError(ValueError):
    pass


def normalize_storage_state(raw: str) -> str:
    source = (raw or '').strip()
    if not source:
        raise BrowserSessionStateError('Session import cannot be empty.')

    try:
        parsed = json.loads(source)
    except json.JSONDecodeError:
        cookies = _normalize_cookie_header(source)
        return json.dumps({'cookies': cookies, 'origins': []})

    if isinstance(parsed, dict) and 'cookies' in parsed:
        cookies = _normalize_cookie_list(parsed.get('cookies'))
        origins = parsed.get('origins', [])
        if not isinstance(origins, list):
            raise BrowserSessionStateError('Storage state origins must be an array when provided.')
        return json.dumps({'cookies': cookies, 'origins': origins})

    if isinstance(parsed, list):
        cookies = _normalize_cookie_list(parsed)
        return json.dumps({'cookies': cookies, 'origins': []})

    if isinstance(parsed, dict):
        cookies = _normalize_cookie_map(parsed)
        return json.dumps({'cookies': cookies, 'origins': []})

    raise BrowserSessionStateError(
        'Unsupported session format. Paste Playwright storage state JSON, a cookie-array JSON export, '
        'a simple cookie map JSON object, or a raw Cookie header.'
    )


def _normalize_cookie_header(raw: str) -> list[dict]:
    cookie_text = raw.strip()
    if cookie_text.lower().startswith('cookie:'):
        cookie_text = cookie_text.split(':', 1)[1].strip()

    cookies = []
    for part in cookie_text.split(';'):
        item = part.strip()
        if not item or '=' not in item:
            continue
        name, value = item.split('=', 1)
        cookies.append(_build_cookie(name.strip(), value.strip()))

    if not cookies:
        raise BrowserSessionStateError(
            'Unsupported session format. Paste Playwright storage state JSON, a cookie-array JSON export, '
            'a simple cookie map JSON object, or a raw Cookie header.'
        )

    return cookies


def _normalize_cookie_map(cookie_map: dict) -> list[dict]:
    cookies = []
    for name, value in cookie_map.items():
        if isinstance(value, (dict, list)):
            raise BrowserSessionStateError('Cookie map values must be plain strings or numbers.')
        cookies.append(_build_cookie(str(name), '' if value is None else str(value)))

    if not cookies:
        raise BrowserSessionStateError('Cookie map must include at least one cookie.')

    return cookies


def _normalize_cookie_list(raw_cookies) -> list[dict]:
    if not isinstance(raw_cookies, list):
        raise BrowserSessionStateError('Cookies must be an array.')

    cookies = []
    for cookie in raw_cookies:
        if not isinstance(cookie, dict):
            raise BrowserSessionStateError('Each cookie must be a JSON object.')

        name = str(cookie.get('name', '')).strip()
        value = cookie.get('value', '')
        if not name:
            raise BrowserSessionStateError('Each cookie must include a name.')

        domain = _coerce_domain(cookie)
        path = str(cookie.get('path') or '/')
        expires = _coerce_expires(cookie)
        secure = bool(cookie.get('secure', True))
        http_only = bool(cookie.get('httpOnly', False))
        same_site = _normalize_same_site(cookie.get('sameSite'))

        cookies.append({
            'name': name,
            'value': '' if value is None else str(value),
            'domain': domain,
            'path': path,
            'expires': expires,
            'httpOnly': http_only,
            'secure': secure,
            'sameSite': same_site,
        })

    if not cookies:
        raise BrowserSessionStateError('Storage state must include at least one cookie.')

    return cookies


def _build_cookie(name: str, value: str) -> dict:
    if not name:
        raise BrowserSessionStateError('Cookie names cannot be empty.')

    return {
        'name': name,
        'value': value,
        'domain': '.x.com',
        'path': '/',
        'expires': -1,
        'httpOnly': False,
        'secure': True,
        'sameSite': 'None',
    }


def _coerce_domain(cookie: dict) -> str:
    domain = cookie.get('domain')
    if domain:
        return str(domain)

    url = cookie.get('url')
    if url:
        parsed = urlparse(str(url))
        if parsed.hostname:
            return parsed.hostname

    return '.x.com'


def _coerce_expires(cookie: dict) -> int | float:
    expires = cookie.get('expires', cookie.get('expirationDate'))
    if expires in (None, '', False):
        return -1

    try:
        return int(expires)
    except (TypeError, ValueError):
        try:
            return float(expires)
        except (TypeError, ValueError) as exc:
            raise BrowserSessionStateError('Cookie expiry must be numeric when provided.') from exc


def _normalize_same_site(value) -> str:
    normalized = str(value or '').strip().lower().replace('_', '').replace('-', '')
    mapping = {
        'lax': 'Lax',
        'strict': 'Strict',
        'none': 'None',
        'norestriction': 'None',
        'unspecified': 'None',
    }
    return mapping.get(normalized, 'None')

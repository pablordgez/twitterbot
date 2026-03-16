import re
from typing import Dict, Any

class CurlParseError(Exception):
    """Exception raised for errors in the cURL parsing process."""
    pass

HEADERS_ALLOWLIST = {
    'authorization',
    'x-csrf-token',
    'x-twitter-auth-type',
    'x-twitter-active-user',
    'x-twitter-client-language',
    'user-agent'
}

COOKIES_ALLOWLIST = {
    'auth_token',
    'ct0',
    'twid'
}

REQUIRED_FIELDS = {
    'authorization',
    'x-csrf-token',
    'auth_token',
    'ct0',
    'twid',
    'queryId'
}

def parse_curl_command(curl_text: str) -> Dict[str, Any]:
    """
    Parses a cURL command manually to extract required Twitter authentication fields.
    Does NOT use subprocess or shlex.
    """
    if len(curl_text) > 50 * 1024:
        raise CurlParseError("Input exceeds 50KB limit")
    
    if curl_text.count('\n') > 500:
        raise CurlParseError("Input exceeds 500 lines limit")
    
    # We will accumulate the extracted data here
    extracted = {
        'headers': {},
        'cookies': {}
    }
    
    # Extract headers. E.g., -H 'authorization: Bearer XYZ'
    # Pattern looks for -H or --header, followed by spaces, an optional quote, and the content.
    header_pattern = re.compile(r'(?i)(?:-H|--header)\s+(["\'])(.*?)\1')
    for match in header_pattern.finditer(curl_text):
        header_str = match.group(2)
        if ':' in header_str:
            key, val = header_str.split(':', 1)
            key = key.strip().lower()
            val = val.strip()
            if key == 'cookie':
                _parse_cookie_string(val, extracted['cookies'])
            elif key in HEADERS_ALLOWLIST:
                extracted['headers'][key] = val

    # Extract cookies via -b or --cookie
    cookie_pattern = re.compile(r'(?i)(?:-b|--cookie)\s+(["\'])(.*?)\1')
    for match in cookie_pattern.finditer(curl_text):
        cookie_str = match.group(2)
        _parse_cookie_string(cookie_str, extracted['cookies'])
    
    # Extract queryId from URL
    # Look for /i/api/graphql/<queryId>/CreateTweet
    url_pattern = re.compile(r'/i/api/graphql/([^/]+)/CreateTweet')
    url_match = url_pattern.search(curl_text)
    if url_match:
        extracted['queryId'] = url_match.group(1)
        
    # Validation against required fields
    missing = []
    for req in REQUIRED_FIELDS:
        if req == 'queryId':
            if 'queryId' not in extracted:
                missing.append('queryId')
        elif req in ['auth_token', 'ct0', 'twid']:
            if req not in extracted['cookies']:
                missing.append(req)
        elif req in ['authorization', 'x-csrf-token']:
            if req not in extracted['headers']:
                missing.append(req)
                
    if missing:
        raise CurlParseError(f"Missing required fields: {', '.join(missing)}")
        
    return extracted

def _parse_cookie_string(cookie_str: str, target_dict: dict):
    """Parses a cookie string (key=val; key2=val2) and updates the target_dict with allowed cookies."""
    parts = cookie_str.split(';')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            k, v = part.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k in COOKIES_ALLOWLIST:
                target_dict[k] = v

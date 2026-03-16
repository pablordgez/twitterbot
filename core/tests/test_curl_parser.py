import pytest
from core.services.curl_parser import parse_curl_command, CurlParseError

def test_parse_curl_valid():
    curl_input = """
    curl 'https://x.com/i/api/graphql/TEST_QUERY_ID/CreateTweet' \\
      -H 'authority: x.com' \\
      -H 'accept: */*' \\
      -H 'authorization: Bearer TEST_BEARER_TOKEN' \\
      -H 'x-csrf-token: TEST_CSRF_TOKEN' \\
      -H 'x-twitter-auth-type: OAuth2Session' \\
      -H 'x-twitter-client-language: en' \\
      -H 'user-agent: Mozilla/5.0' \\
      -H 'cookie: auth_token=TEST_AUTH_TOKEN; ct0=TEST_CT0; twid=TEST_TWID; other=ignoreme' \\
      --data-raw '{"variables":{}}'
    """
    
    result = parse_curl_command(curl_input)
    
    assert result['queryId'] == 'TEST_QUERY_ID'
    assert result['headers']['authorization'] == 'Bearer TEST_BEARER_TOKEN'
    assert result['headers']['x-csrf-token'] == 'TEST_CSRF_TOKEN'
    assert result['headers']['x-twitter-auth-type'] == 'OAuth2Session'
    assert result['headers']['user-agent'] == 'Mozilla/5.0'
    
    assert 'authority' not in result['headers']
    
    assert result['cookies']['auth_token'] == 'TEST_AUTH_TOKEN'
    assert result['cookies']['ct0'] == 'TEST_CT0'
    assert result['cookies']['twid'] == 'TEST_TWID'
    assert 'other' not in result['cookies']

def test_parse_curl_missing_query_id():
    curl_input = """
    curl 'https://x.com/some/other/url' \\
      -H 'authorization: Bearer A' \\
      -H 'x-csrf-token: B' \\
      -H 'cookie: auth_token=C; ct0=D; twid=E;'
    """
    with pytest.raises(CurlParseError, match="Missing required fields.*queryId"):
        parse_curl_command(curl_input)

def test_parse_curl_missing_cookie():
    curl_input = """
    curl 'https://x.com/i/api/graphql/QID/CreateTweet' \\
      -H 'authorization: Bearer A' \\
      -H 'x-csrf-token: B' \\
      -H 'cookie: auth_token=C; twid=E;'
    """
    with pytest.raises(CurlParseError, match="Missing required fields.*ct0"):
        parse_curl_command(curl_input)

def test_parse_curl_missing_header():
    curl_input = """
    curl 'https://x.com/i/api/graphql/QID/CreateTweet' \\
      -H 'authorization: Bearer A' \\
      -H 'cookie: auth_token=C; ct0=D; twid=E;'
    """
    with pytest.raises(CurlParseError, match="Missing required fields.*x-csrf-token"):
        parse_curl_command(curl_input)

def test_parse_curl_with_b_flag():
    curl_input = """
    curl 'https://x.com/i/api/graphql/QID/CreateTweet' \\
      -H 'authorization: A' \\
      -H 'x-csrf-token: B' \\
      -b 'auth_token=C; ct0=D; twid=E'
    """
    result = parse_curl_command(curl_input)
    assert result['cookies']['auth_token'] == 'C'

def test_parse_curl_size_limit():
    curl_input = "a" * (50 * 1024 + 1)
    with pytest.raises(CurlParseError, match="50KB"):
        parse_curl_command(curl_input)
        
def test_parse_curl_lines_limit():
    curl_input = "a\\n" * 501
    with pytest.raises(CurlParseError, match="500 lines"):
        parse_curl_command(curl_input)

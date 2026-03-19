def interpret_create_tweet_response(data: dict) -> tuple[bool, str]:
    """
    X can return HTTP 200 while still rejecting the mutation at the GraphQL layer.
    Treat the response as success only when it contains a concrete tweet identifier.
    """
    if not isinstance(data, dict):
        return False, 'Unexpected response format from server'

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
        return False, 'CreateTweet response missing result payload'

    rest_id = result.get('rest_id')
    legacy_id = result.get('legacy', {}).get('id_str') if isinstance(result.get('legacy'), dict) else None
    typename = result.get('__typename')

    if rest_id or legacy_id:
        return True, ''

    if typename:
        return False, f'CreateTweet returned {typename} without a tweet id'

    return False, 'CreateTweet response missing tweet id'

from django.conf import settings
from django.core.exceptions import ValidationError

def validate_tweet_length(text: str):
    """
    Validates the length of a tweet based on project settings.
    """
    min_length = getattr(settings, 'TWEET_MIN_LENGTH', 1)
    max_length = getattr(settings, 'TWEET_MAX_LENGTH', 280)
    
    length = len(text)
    
    if length < min_length:
        raise ValidationError(f"Tweet is too short. Minimum length is {min_length} characters.")
    
    if length > max_length:
        raise ValidationError(f"Tweet is too long. Maximum length is {max_length} characters (current: {length}).")
    
    return True

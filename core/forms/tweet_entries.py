from django import forms
from core.models.tweets import TweetEntry
from core.services.tweet_validation import validate_tweet_length

class TweetEntryForm(forms.ModelForm):
    class Meta:
        model = TweetEntry
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter tweet text...',
            }),
        }

    def clean_text(self):
        text = self.cleaned_data.get('text')
        validate_tweet_length(text)
        return text

    def clean(self):
        cleaned_data = super().clean()
        text = cleaned_data.get('text')
        tweet_list = getattr(self, 'tweet_list', None)
        
        if text and tweet_list:
            # Check for duplicates in the same list
            is_duplicate = TweetEntry.objects.filter(list=tweet_list, text=text).exists()
            if is_duplicate:
                # We add a custom attribute to indicate a duplicate was found
                # The view can then decide how to handle the warning
                self.is_duplicate = True
        
        return cleaned_data

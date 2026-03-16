from django import forms
from ..models.tweets import TweetList

class TweetListForm(forms.ModelForm):
    class Meta:
        model = TweetList
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter list name...',
                'maxlength': '255',
            })
        }

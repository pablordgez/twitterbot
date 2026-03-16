from django import forms
from core.models.accounts import PostingAccount
from core.services.curl_parser import parse_curl_command, CurlParseError

class PostingAccountForm(forms.ModelForm):
    class Meta:
        model = PostingAccount
        fields = ['name', 'is_active', 'notification_mode']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'notification_mode': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class CurlImportForm(forms.Form):
    curl_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': "curl 'https://x.com/i/api/graphql/...\\n  -H 'authorization: Beare..."
        }),
        help_text='Paste the "Copy as cURL (bash)" output from Twitter/X network requests.'
    )

    def clean_curl_text(self):
        text = self.cleaned_data.get('curl_text', '')
        try:
            parsed = parse_curl_command(text)
            return parsed
        except CurlParseError as e:
            raise forms.ValidationError(str(e))

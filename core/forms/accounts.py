from django import forms
from core.models.accounts import PostingAccount
from core.services.curl_parser import parse_curl_command, CurlParseError

class PostingAccountForm(forms.ModelForm):
    class Meta:
        model = PostingAccount
        fields = ['name', 'auth_mode', 'is_active', 'notification_mode']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'auth_mode': forms.Select(attrs={'class': 'form-select'}),
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


class BrowserCredentialForm(forms.Form):
    username = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'username',
        }),
        help_text='Username, email, or phone number accepted by the X login flow.',
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
        }),
        help_text='Stored encrypted. Some accounts may still require challenge or 2FA in the browser flow.',
    )


class BrowserSessionStateForm(forms.Form):
    storage_state = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 8,
            'placeholder': '{"cookies": [...], "origins": [...]}',
        }),
        help_text='Paste a Playwright storage state JSON captured from a real logged-in browser session.',
    )

    def clean_storage_state(self):
        import json

        raw = self.cleaned_data['storage_state']
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f'Invalid JSON: {exc.msg}') from exc

        if not isinstance(parsed, dict):
            raise forms.ValidationError('Storage state must be a JSON object.')

        if 'cookies' not in parsed:
            raise forms.ValidationError('Storage state must include a cookies array.')

        return raw

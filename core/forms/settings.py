from django import forms
from core.models.notifications import SMTPSettings, NotificationRecipient
from core.services.encryption import encrypt

class SMTPSettingsForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        required=False,
        help_text="Leave blank to keep existing password."
    )

    class Meta:
        model = SMTPSettings
        fields = ['host', 'port', 'username', 'sender_email', 'use_tls', 'use_starttls']
        widgets = {
            'host': forms.TextInput(attrs={'class': 'form-control'}),
            'port': forms.NumberInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'sender_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'use_tls': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'use_starttls': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.pk and self.instance.encrypted_password:
            self.fields['password'].widget.attrs['placeholder'] = '•••••••• (Encrypted)'

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            instance.encrypted_password = encrypt(password)
        if commit:
            instance.save()
        return instance

class NotificationRecipientForm(forms.ModelForm):
    class Meta:
        model = NotificationRecipient
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@example.com'}),
        }

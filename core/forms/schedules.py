"""
Schedule forms for T-012.

Provides ScheduleForm for creating/editing one-time and recurring schedules
with timezone selection, content mode toggling, and multi-account assignment.
"""
from django import forms
from django.conf import settings

from core.models.accounts import PostingAccount
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.tweets import TweetList
from core.services.schedule_logic import validate_schedule


TIMEZONE_MODE_CHOICES = [
    ('system', f'System timezone'),
    ('utc', 'UTC'),
    ('other', 'Other…'),
]


class ScheduleForm(forms.ModelForm):
    """Form for creating and editing schedules."""

    # --- Non-model fields ---
    timezone_mode = forms.ChoiceField(
        choices=TIMEZONE_MODE_CHOICES,
        initial='system',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True,
    )
    timezone_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. America/New_York',
            'list': 'tz-list',
        }),
        help_text='Enter an IANA timezone name.',
    )
    target_accounts = forms.ModelMultipleChoiceField(
        queryset=PostingAccount.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        error_messages={'required': 'At least one target account is required.'},
    )
    source_lists = forms.ModelMultipleChoiceField(
        queryset=TweetList.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
    )

    class Meta:
        model = Schedule
        fields = [
            'schedule_type', 'start_datetime', 'content_mode',
            'fixed_content', 'interval_type', 'interval_value',
            'random_resolution_mode', 'reuse_enabled', 'exhaustion_behavior',
        ]
        widgets = {
            'schedule_type': forms.RadioSelect(
                choices=Schedule.ScheduleType.choices,
                attrs={'class': 'form-check-input'},
            ),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'content_mode': forms.RadioSelect(
                choices=Schedule.ContentMode.choices,
                attrs={'class': 'form-check-input'},
            ),
            'fixed_content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter your tweet text…',
            }),
            'interval_type': forms.Select(
                choices=[('', '---')] + list(Schedule.IntervalType.choices),
                attrs={'class': 'form-select'},
            ),
            'interval_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1',
            }),
            'random_resolution_mode': forms.RadioSelect(
                choices=Schedule.RandomResolutionMode.choices,
                attrs={'class': 'form-check-input'},
            ),
            'reuse_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'exhaustion_behavior': forms.Select(
                choices=[('', '---')] + list(Schedule.ExhaustionBehavior.choices),
                attrs={'class': 'form-select'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make recurring-only fields not required at form level
        # (validated in clean())
        self.fields['interval_type'].required = False
        self.fields['interval_value'].required = False
        self.fields['fixed_content'].required = False
        self.fields['random_resolution_mode'].required = False
        self.fields['exhaustion_behavior'].required = False

        # Provide the system timezone label
        self.system_tz = settings.TIME_ZONE
        self.fields['timezone_mode'].choices = [
            ('system', f'System timezone ({self.system_tz})'),
            ('utc', 'UTC'),
            ('other', 'Other…'),
        ]

        # For editing: pre-populate timezone_mode from existing timezone_name
        if self.instance and self.instance.pk:
            tz_name = self.instance.timezone_name
            if tz_name == self.system_tz:
                self.initial['timezone_mode'] = 'system'
            elif tz_name == 'UTC':
                self.initial['timezone_mode'] = 'utc'
            else:
                self.initial['timezone_mode'] = 'other'
                self.initial['timezone_other'] = tz_name

            # Pre-populate target accounts
            self.initial['target_accounts'] = list(
                ScheduleTargetAccount.objects.filter(
                    schedule=self.instance,
                ).values_list('account_id', flat=True)
            )
            # Pre-populate source lists
            self.initial['source_lists'] = list(
                ScheduleSourceList.objects.filter(
                    schedule=self.instance,
                ).values_list('tweet_list_id', flat=True)
            )

        # Fix datetime-local format for input
        self.fields['start_datetime'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S',
        ]

    def _resolve_timezone_name(self):
        """Resolve the timezone_name from timezone_mode + timezone_other."""
        mode = self.cleaned_data.get('timezone_mode', 'system')
        if mode == 'system':
            return self.system_tz
        elif mode == 'utc':
            return 'UTC'
        else:
            return self.cleaned_data.get('timezone_other', '').strip()

    def clean(self):
        cleaned = super().clean()

        # Resolve timezone
        tz_name = self._resolve_timezone_name()
        if not tz_name:
            self.add_error('timezone_other', 'Please specify a timezone.')
            return cleaned

        # Temporarily set timezone_name on instance for validation
        self.instance.timezone_name = tz_name
        self.instance.timezone_mode = cleaned.get('timezone_mode', 'system')

        # Collect IDs for validation
        target_accounts = cleaned.get('target_accounts', [])
        target_account_ids = [a.pk for a in target_accounts]

        source_lists = cleaned.get('source_lists', [])
        source_list_ids = [sl.pk for sl in source_lists]

        # Apply form fields to instance so validate_schedule works
        for field in self.Meta.fields:
            if field in cleaned:
                setattr(self.instance, field, cleaned[field])

        # Run schedule business logic validation
        errors = validate_schedule(
            self.instance,
            target_account_ids=target_account_ids,
            source_list_ids=source_list_ids,
        )

        for error_msg in errors:
            self.add_error(None, error_msg)

        return cleaned

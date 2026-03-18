from django import forms
from ..models import PostingAccount, Schedule

class HistoryFilterForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=PostingAccount.objects.all(),
        required=False,
        empty_label="All Accounts",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    schedule = forms.ModelChoiceField(
        queryset=Schedule.objects.all(),
        required=False,
        empty_label="All Schedules",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        choices=[
            ('', 'All Statuses'),
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('missed', 'Missed'),
            ('skipped', 'Skipped'),
            ('canceled', 'Canceled')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search log...'})
    )

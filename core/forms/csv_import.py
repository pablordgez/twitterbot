from django import forms
from core.models.tweets import TweetList

class CSVImportForm(forms.Form):
    target_list = forms.ModelChoiceField(
        queryset=TweetList.objects.all(),
        label="Target Tweet List",
        help_text="Select the list where tweets will be imported.",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    import_mode = forms.ChoiceField(
        choices=[('file', 'Upload CSV File'), ('paste', 'Paste CSV Text')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'hx-get': '#', 'hx-target': '#upload-fields-container'}),
        initial='file'
    )
    
    csv_file = forms.FileField(
        required=False,
        label="CSV File",
        help_text="Max 5MB.",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'})
    )
    
    csv_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
        label="CSV Text",
        help_text="Paste your CSV content here."
    )

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get('import_mode')
        file = cleaned_data.get('csv_file')
        text = cleaned_data.get('csv_text')

        if mode == 'file':
            if not file:
                self.add_error('csv_file', "Please provide a CSV file.")
            elif file.size > 5 * 1024 * 1024:
                self.add_error('csv_file', "File size exceeds 5MB limit.")
        elif mode == 'paste':
            if not text:
                self.add_error('csv_text', "Please paste CSV content.")

        return cleaned_data

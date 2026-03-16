from django.views.generic import FormView
from django.urls import reverse_lazy
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from core.forms.csv_import import CSVImportForm
from core.services.csv_import import process_csv_content
from core.models.tweets import TweetList

class CSVImportView(LoginRequiredMixin, FormView):
    template_name = 'tweets/csv_import.html'
    form_class = CSVImportForm
    
    def get_initial(self):
        initial = super().get_initial()
        if 'list_pk' in self.kwargs:
            initial['target_list'] = get_object_or_404(TweetList, pk=self.kwargs['list_pk'])
        return initial

    def form_valid(self, form):
        mode = form.cleaned_data['import_mode']
        target_list = form.cleaned_data['target_list']
        
        if mode == 'file':
            csv_file = form.cleaned_data['csv_file']
            # Read and decode
            content = csv_file.read().decode('utf-8-sig', errors='replace')
        else:
            content = form.cleaned_data['csv_text']
            
        imported_count, rejected = process_csv_content(content, target_list)
        
        return render(self.request, 'tweets/csv_result.html', {
            'target_list': target_list,
            'imported_count': imported_count,
            'rejected': rejected,
            'total_processed': imported_count + len(rejected)
        })

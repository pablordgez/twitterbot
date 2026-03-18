from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from ..models import HistoryEvent
from ..forms.history import HistoryFilterForm

class HistoryListView(LoginRequiredMixin, ListView):
    model = HistoryEvent
    context_object_name = 'events'
    paginate_by = 25
    ordering = ['-timestamp']

    def get_queryset(self):
        queryset = super().get_queryset()
        self.form = HistoryFilterForm(self.request.GET)

        if self.form.is_valid():
            if self.form.cleaned_data.get('account'):
                queryset = queryset.filter(account=self.form.cleaned_data['account'])
            if self.form.cleaned_data.get('schedule'):
                queryset = queryset.filter(schedule=self.form.cleaned_data['schedule'])
            if self.form.cleaned_data.get('status'):
                queryset = queryset.filter(result_status=self.form.cleaned_data['status'])
            if self.form.cleaned_data.get('date_from'):
                queryset = queryset.filter(timestamp__date__gte=self.form.cleaned_data['date_from'])
            if self.form.cleaned_data.get('date_to'):
                queryset = queryset.filter(timestamp__date__lte=self.form.cleaned_data['date_to'])
            if self.form.cleaned_data.get('search'):
                search_query = self.form.cleaned_data['search']
                queryset = queryset.filter(
                    Q(content_summary__icontains=search_query) |
                    Q(event_type__icontains=search_query)
                )

                # Cannot simply do detail__icontains on JSONField with SQLite using older Django in a way that is universally supported.
                # However, since we are using Django 5.x on SQLite, it provides JSON1 extension out of the box, but we might want to just text search it
                # if we treat JSON as string or ignore JSON body for search to avoid DB error. I'll add search over correlation_id instead of JSON details.
                queryset = queryset | super().get_queryset().filter(correlation_id__icontains=search_query)

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['history/list_results.html']
        return ['history/list.html']


class HistoryDetailRowView(LoginRequiredMixin, DetailView):
    model = HistoryEvent
    context_object_name = 'event'

    def get_template_names(self):
        if self.request.GET.get('collapse') == 'true':
            return ['history/list_row.html']
        return ['history/detail_row.html']

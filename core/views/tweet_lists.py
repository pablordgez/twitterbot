from django.shortcuts import get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count

from ..models.tweets import TweetList, TweetEntry
from ..services.history import log_event
from ..forms.tweet_lists import TweetListForm
from ..forms.tweet_entries import TweetEntryForm
from ..services.dependency_cascade import check_list_dependencies, cascade_cancel

class TweetListListView(LoginRequiredMixin, ListView):
    model = TweetList
    template_name = 'tweets/list_index.html'
    context_object_name = 'tweet_lists'

    def get_queryset(self):
        return TweetList.objects.annotate(entry_count=Count('entries')).order_by('-created_at')

class TweetListCreateView(LoginRequiredMixin, CreateView):
    model = TweetList
    form_class = TweetListForm
    template_name = 'tweets/list_form.html'
    success_url = reverse_lazy('core:tweet_list_list')

    def form_valid(self, form):
        messages.success(self.request, "Tweet list created successfully.")
        return super().form_valid(form)

class TweetListUpdateView(LoginRequiredMixin, UpdateView):
    model = TweetList
    form_class = TweetListForm
    template_name = 'tweets/list_form.html'
    success_url = reverse_lazy('core:tweet_list_list')

    def form_valid(self, form):
        messages.success(self.request, "Tweet list updated successfully.")
        return super().form_valid(form)

class TweetListDeleteView(LoginRequiredMixin, DeleteView):
    model = TweetList
    template_name = 'tweets/list_delete_confirm.html'
    success_url = reverse_lazy('core:tweet_list_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['affected_schedules'] = check_list_dependencies(self.object)
        return context

    def form_valid(self, form):
        affected = check_list_dependencies(self.object)
        with transaction.atomic():
            if affected:
                cascade_cancel(affected, 'list_deleted')
            log_event(
                event_type='DEPENDENCY_DELETE_CONFIRMED',
                detail={'deleted': 'tweet_list', 'name': self.object.name},
                result_status='confirmed',
            )
            messages.success(self.request, "Tweet list deleted and linked schedules canceled.")
            return super().form_valid(form)

class TweetListDetailView(LoginRequiredMixin, ListView):
    model = TweetEntry
    template_name = 'tweets/list_detail.html'
    context_object_name = 'entries'
    paginate_by = 50

    def get_queryset(self):
        self.tweet_list = get_object_or_404(TweetList, pk=self.kwargs['pk'])
        return TweetEntry.objects.filter(list=self.tweet_list).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tweet_list'] = self.tweet_list
        context['form'] = TweetEntryForm()
        return context

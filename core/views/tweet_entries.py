from django.shortcuts import render, get_object_or_404
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse

from ..models.tweets import TweetList, TweetEntry
from ..forms.tweet_entries import TweetEntryForm

class TweetEntryCreateView(LoginRequiredMixin, CreateView):
    model = TweetEntry
    form_class = TweetEntryForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.tweet_list = get_object_or_404(TweetList, pk=self.kwargs['list_pk'])
        kwargs['tweet_list'] = self.tweet_list
        return kwargs

    def form_valid(self, form):
        form.instance.list = self.tweet_list
        # Check for duplicate warning
        is_duplicate = getattr(form, 'is_duplicate', False)
        # We allow saving even if it's a duplicate, but we'll show a warning in the response
        response = super().form_valid(form)

        if self.request.headers.get('HX-Request'):
            # Return partial for the row
            return render(self.request, 'tweets/entry_row.html', {
                'entry': self.object,
                'tweet_list': self.tweet_list,
                'is_duplicate': is_duplicate
            })

        if is_duplicate:
            messages.warning(self.request, "Entry added, but it's a duplicate of an existing entry in this list.")
        else:
            messages.success(self.request, "Entry added successfully.")

        return response

    def get_success_url(self):
        return reverse('core:tweet_list_detail', kwargs={'pk': self.kwargs['list_pk']})

class TweetEntryUpdateView(LoginRequiredMixin, UpdateView):
    model = TweetEntry
    form_class = TweetEntryForm
    template_name = 'tweets/entry_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tweet_list'] = self.object.list
        return kwargs

    def form_valid(self, form):
        is_duplicate = getattr(form, 'is_duplicate', False)
        response = super().form_valid(form)

        if self.request.headers.get('HX-Request'):
            return render(self.request, 'tweets/entry_row.html', {
                'entry': self.object,
                'tweet_list': self.object.list,
                'is_duplicate': is_duplicate
            })

        if is_duplicate:
            messages.warning(self.request, "Entry updated, but it's now a duplicate.")
        else:
            messages.success(self.request, "Entry updated successfully.")

        return response

    def get_success_url(self):
        return reverse('core:tweet_list_detail', kwargs={'pk': self.object.list.pk})

class TweetEntryDeleteView(LoginRequiredMixin, DeleteView):
    model = TweetEntry

    def get_success_url(self):
        return reverse('core:tweet_list_detail', kwargs={'pk': self.object.list.pk})

    def form_valid(self, form):
        self.object = self.get_object()
        list_pk = self.object.list.pk

        success_url = self.get_success_url()
        self.object.delete()

        if self.request.headers.get('HX-Request'):
            return HttpResponse("") # Empty response removes the item in HTMX

        messages.success(self.request, "Entry deleted.")
        from django.shortcuts import redirect
        return redirect(success_url)

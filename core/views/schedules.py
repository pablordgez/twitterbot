"""
Schedule views for T-012.

List, create, edit, detail, and cancel views plus HTMX partials for
conditional field toggling on the schedule form.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.forms.schedules import ScheduleForm
from core.models.accounts import PostingAccount
from core.models.schedules import Schedule, ScheduleSourceList, ScheduleTargetAccount
from core.models.tweets import TweetList
from core.services.schedule_logic import increment_version


# ──────────────────────────────────────────────────
# Standard CRUD views
# ──────────────────────────────────────────────────


class ScheduleListView(LoginRequiredMixin, ListView):
    model = Schedule
    template_name = 'schedules/list.html'
    context_object_name = 'schedules'
    ordering = ['-created_at']


class ScheduleCreateView(LoginRequiredMixin, CreateView):
    model = Schedule
    form_class = ScheduleForm
    template_name = 'schedules/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['show_recurring'] = False
        ctx['show_dst_indicator'] = False
        return ctx

    def get_success_url(self):
        return reverse('core:schedule_list')

    def form_valid(self, form):
        with transaction.atomic():
            # Save the schedule itself
            self.object = form.save(commit=False)
            self.object.timezone_name = form._resolve_timezone_name()
            self.object.timezone_mode = form.cleaned_data.get('timezone_mode', 'system')
            self.object.save()

            # Create join records
            for account in form.cleaned_data.get('target_accounts', []):
                ScheduleTargetAccount.objects.create(
                    schedule=self.object, account=account,
                )
            for tweet_list in form.cleaned_data.get('source_lists', []):
                ScheduleSourceList.objects.create(
                    schedule=self.object, tweet_list=tweet_list,
                )

        messages.success(self.request, 'Schedule created successfully.')
        return redirect(self.get_success_url())


class ScheduleUpdateView(LoginRequiredMixin, UpdateView):
    model = Schedule
    form_class = ScheduleForm
    template_name = 'schedules/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['show_recurring'] = (
            self.object.schedule_type == Schedule.ScheduleType.RECURRING
        )
        ctx['show_dst_indicator'] = (
            self.object.schedule_type == Schedule.ScheduleType.RECURRING
            and self.object.timezone_name != 'UTC'
        )
        return ctx

    def get_success_url(self):
        return reverse('core:schedule_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.timezone_name = form._resolve_timezone_name()
            self.object.timezone_mode = form.cleaned_data.get('timezone_mode', 'system')
            self.object.save()

            # Increment version
            increment_version(self.object)

            # Recreate join records
            ScheduleTargetAccount.objects.filter(schedule=self.object).delete()
            for account in form.cleaned_data.get('target_accounts', []):
                ScheduleTargetAccount.objects.create(
                    schedule=self.object, account=account,
                )

            ScheduleSourceList.objects.filter(schedule=self.object).delete()
            for tweet_list in form.cleaned_data.get('source_lists', []):
                ScheduleSourceList.objects.create(
                    schedule=self.object, tweet_list=tweet_list,
                )

        messages.success(self.request, 'Schedule updated successfully.')
        return redirect(self.get_success_url())


class ScheduleDetailView(LoginRequiredMixin, DetailView):
    model = Schedule
    template_name = 'schedules/detail.html'
    context_object_name = 'schedule'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['target_accounts'] = PostingAccount.objects.filter(
            scheduletargetaccount__schedule=self.object,
        )
        ctx['source_lists'] = TweetList.objects.filter(
            schedulesourcelist__schedule=self.object,
        )
        # DST indicator for non-UTC recurring schedules
        ctx['show_dst_indicator'] = (
            self.object.schedule_type == Schedule.ScheduleType.RECURRING
            and self.object.timezone_name != 'UTC'
        )
        return ctx


class ScheduleCancelView(LoginRequiredMixin, View):
    """POST-only: cancel a schedule."""

    def post(self, request, pk):
        schedule = get_object_or_404(Schedule, pk=pk)
        schedule.status = 'canceled'
        schedule.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Schedule canceled.')
        return redirect('core:schedule_list')


# ──────────────────────────────────────────────────
# HTMX partial views
# ──────────────────────────────────────────────────


class RecurringFieldsPartialView(LoginRequiredMixin, View):
    """Return the recurring-only fields partial via HTMX."""

    def get(self, request):
        schedule_type = request.GET.get('schedule_type', 'one_time')
        show = schedule_type == 'recurring'
        form = ScheduleForm()
        return render(request, 'schedules/partials/recurring_fields.html', {
            'form': form,
            'show_recurring': show,
        })


class ContentModePartialView(LoginRequiredMixin, View):
    """Return the content-mode conditional fields partial via HTMX."""

    def get(self, request):
        content_mode = request.GET.get('content_mode', 'fixed_new')
        form = ScheduleForm()
        return render(request, 'schedules/partials/content_mode.html', {
            'form': form,
            'content_mode': content_mode,
        })

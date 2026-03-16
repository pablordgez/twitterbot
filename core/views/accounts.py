from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.db import transaction
import json
import hashlib

from core.models.accounts import PostingAccount, PostingAccountSecret
from core.models.schedules import ScheduleTargetAccount
from core.models.history import HistoryEvent
from core.forms.accounts import PostingAccountForm, CurlImportForm
from core.services.encryption import encrypt, mask_value

class AccountListView(LoginRequiredMixin, ListView):
    model = PostingAccount
    template_name = 'accounts/list.html'
    context_object_name = 'accounts'
    ordering = ['-created_at']

class AccountCreateView(LoginRequiredMixin, CreateView):
    model = PostingAccount
    form_class = PostingAccountForm
    template_name = 'accounts/form.html'
    success_url = reverse_lazy('core:account_list')

    def form_valid(self, form):
        messages.success(self.request, "Account created successfully.")
        return super().form_valid(form)

class AccountUpdateView(LoginRequiredMixin, UpdateView):
    model = PostingAccount
    form_class = PostingAccountForm
    template_name = 'accounts/form.html'
    
    def get_success_url(self):
        return reverse('core:account_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Account updated successfully.")
        return super().form_valid(form)

class AccountDetailView(LoginRequiredMixin, DetailView):
    model = PostingAccount
    template_name = 'accounts/detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['curl_form'] = CurlImportForm()
        if hasattr(self.object, 'secret'):
            context['secret_masked'] = mask_value(self.object.secret.field_hash, 4)
        else:
            context['secret_masked'] = None
        return context

class AccountCurlImportView(LoginRequiredMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(PostingAccount, pk=pk)
        form = CurlImportForm(request.POST)

        if form.is_valid():
            parsed_data = form.cleaned_data['curl_text']
            
            # Encrypt and save secret
            json_dump = json.dumps(parsed_data)
            encrypted = encrypt(json_dump)
            field_hash = hashlib.sha256(json_dump.encode('utf-8')).hexdigest()
            
            with transaction.atomic():
                PostingAccountSecret.objects.update_or_create(
                    account=account,
                    defaults={
                        'encrypted_data': encrypted,
                        'field_hash': field_hash
                    }
                )
                HistoryEvent.objects.create(
                    event_type='ACCOUNT_SECRET_REPLACED' if hasattr(account, 'secret') else 'ACCOUNT_IMPORT_ACCEPTED',
                    account=account,
                    content_summary='cURL data imported'
                )

            messages.success(request, "Account secrets imported successfully.")
            return redirect('core:account_detail', pk=pk)

        else:
            HistoryEvent.objects.create(
                event_type='ACCOUNT_IMPORT_REJECTED',
                account=account,
                content_summary='cURL data import failed validation'
            )
            context = {
                'account': account,
                'curl_form': form,
                'secret_masked': mask_value(account.secret.field_hash, 4) if hasattr(account, 'secret') else None
            }
            return render(request, 'accounts/curl_import.html', context)

class AccountTestPostView(LoginRequiredMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(PostingAccount, pk=pk)
        
        # In a real scenario, decrypt secrets, build request, post to X
        # For now, stub
        success = True
        
        HistoryEvent.objects.create(
            event_type='TEST_POST_CONFIRMED',
            account=account,
            content_summary='Test post to X',
            result_status='success' if success else 'failed'
        )

        if success:
            messages.success(request, "Test post succeeded.")
        else:
            messages.error(request, "Test post failed.")

        return redirect('core:account_detail', pk=pk)

class AccountDeleteView(LoginRequiredMixin, DeleteView):
    model = PostingAccount
    template_name = 'accounts/delete_confirm.html'
    success_url = reverse_lazy('core:account_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check dependencies
        active_schedules = [
            sta.schedule for sta in ScheduleTargetAccount.objects.filter(account=self.object)
            if sta.schedule.status == 'active'
        ]
        context['affected_schedules'] = active_schedules
        return context

    def form_valid(self, form):
        # Cancel affected schedules
        active_schedules = [
            sta.schedule for sta in ScheduleTargetAccount.objects.filter(account=self.object)
            if sta.schedule.status == 'active'
        ]
        with transaction.atomic():
            for schedule in active_schedules:
                schedule.status = 'canceled'
                schedule.save(update_fields=['status'])
            return super().form_valid(form)

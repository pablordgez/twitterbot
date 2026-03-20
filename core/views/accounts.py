from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.db import transaction
import json
import hashlib
from uuid import uuid4

from core.models.accounts import PostingAccount, PostingAccountSecret, PostingAccountBrowserCredential
from core.services.history import log_event
from core.forms.accounts import (
    PostingAccountForm,
    CurlImportForm,
    BrowserCredentialForm,
    BrowserSessionStateForm,
)
from core.services.encryption import encrypt, mask_value
from core.services.dependency_cascade import check_account_dependencies, cascade_cancel

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
        response = super().form_valid(form)
        log_event(
            event_type='ACCOUNT_CREATED',
            account=self.object,
            result_status='success',
        )
        messages.success(self.request, "Account created successfully.")
        return response

class AccountUpdateView(LoginRequiredMixin, UpdateView):
    model = PostingAccount
    form_class = PostingAccountForm
    template_name = 'accounts/form.html'

    def get_success_url(self):
        return reverse('core:account_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        log_event(
            event_type='ACCOUNT_UPDATED',
            account=self.object,
            result_status='success',
        )
        messages.success(self.request, "Account updated successfully.")
        return response

class AccountDetailView(LoginRequiredMixin, DetailView):
    model = PostingAccount
    template_name = 'accounts/detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['curl_form'] = CurlImportForm()
        context['browser_form'] = BrowserCredentialForm()
        context['browser_session_form'] = BrowserSessionStateForm()
        if hasattr(self.object, 'secret'):
            context['secret_masked'] = mask_value(self.object.secret.field_hash, 4)
        else:
            context['secret_masked'] = None
        context['browser_credentials_configured'] = hasattr(self.object, 'browser_credential')
        context['browser_session_configured'] = bool(
            hasattr(self.object, 'browser_credential') and self.object.browser_credential.encrypted_storage_state
        )
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
                is_replacement = hasattr(account, 'secret')
                PostingAccountSecret.objects.update_or_create(
                    account=account,
                    defaults={
                        'encrypted_data': encrypted,
                        'field_hash': field_hash
                    }
                )
                log_event(
                    event_type='ACCOUNT_SECRET_REPLACED' if is_replacement else 'ACCOUNT_IMPORT_ACCEPTED',
                    account=account,
                    content_summary='cURL data imported'
                )

            messages.success(request, "Account secrets imported successfully.")
            return redirect('core:account_detail', pk=pk)

        else:
            log_event(
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


class AccountBrowserCredentialView(LoginRequiredMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(PostingAccount, pk=pk)
        form = BrowserCredentialForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            with transaction.atomic():
                is_replacement = hasattr(account, 'browser_credential')
                PostingAccountBrowserCredential.objects.update_or_create(
                    account=account,
                    defaults={
                        'encrypted_username': encrypt(username),
                        'encrypted_password': encrypt(password),
                    },
                )
                if account.auth_mode != PostingAccount.AuthMode.BROWSER:
                    account.auth_mode = PostingAccount.AuthMode.BROWSER
                    account.save(update_fields=['auth_mode', 'updated_at'])

                log_event(
                    event_type='ACCOUNT_BROWSER_CREDENTIALS_REPLACED' if is_replacement else 'ACCOUNT_BROWSER_CREDENTIALS_SAVED',
                    account=account,
                    content_summary='Browser login credentials saved',
                    result_status='success',
                )

            messages.success(request, 'Browser login credentials saved successfully.')
            return redirect('core:account_detail', pk=pk)

        context = {
            'account': account,
            'curl_form': CurlImportForm(),
            'browser_form': form,
            'browser_session_form': BrowserSessionStateForm(),
            'secret_masked': mask_value(account.secret.field_hash, 4) if hasattr(account, 'secret') else None,
            'browser_credentials_configured': hasattr(account, 'browser_credential'),
            'browser_session_configured': bool(
                hasattr(account, 'browser_credential') and account.browser_credential.encrypted_storage_state
            ),
        }
        return render(request, 'accounts/detail.html', context)


class AccountBrowserSessionStateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(PostingAccount, pk=pk)
        form = BrowserSessionStateForm(request.POST)

        if form.is_valid():
            storage_state = form.cleaned_data['storage_state']

            with transaction.atomic():
                credential_defaults = {
                    'encrypted_storage_state': encrypt(storage_state),
                }
                if not hasattr(account, 'browser_credential'):
                    credential_defaults['encrypted_username'] = encrypt('')
                    credential_defaults['encrypted_password'] = encrypt('')

                PostingAccountBrowserCredential.objects.update_or_create(
                    account=account,
                    defaults=credential_defaults,
                )

                if account.auth_mode != PostingAccount.AuthMode.BROWSER:
                    account.auth_mode = PostingAccount.AuthMode.BROWSER
                    account.save(update_fields=['auth_mode', 'updated_at'])

                log_event(
                    event_type='ACCOUNT_BROWSER_SESSION_SAVED',
                    account=account,
                    content_summary='Browser storage state saved',
                    result_status='success',
                )

            messages.success(request, 'Browser session state saved successfully.')
            return redirect('core:account_detail', pk=pk)

        context = {
            'account': account,
            'curl_form': CurlImportForm(),
            'browser_form': BrowserCredentialForm(),
            'browser_session_form': form,
            'secret_masked': mask_value(account.secret.field_hash, 4) if hasattr(account, 'secret') else None,
            'browser_credentials_configured': hasattr(account, 'browser_credential'),
            'browser_session_configured': bool(
                hasattr(account, 'browser_credential') and account.browser_credential.encrypted_storage_state
            ),
        }
        return render(request, 'accounts/detail.html', context)

class AccountTestPostView(LoginRequiredMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(PostingAccount, pk=pk)
        correlation_id = uuid4().hex

        log_event(
            event_type='TEST_POST_CONFIRMED',
            account=account,
            content_summary='test',
            result_status='confirmed',
            correlation_id=correlation_id,
        )

        from core.services.posting_executor import execute_test_post
        success, error_detail = execute_test_post(account, content='test')

        log_event(
            event_type='TEST_POST_SUCCEEDED' if success else 'TEST_POST_FAILED',
            account=account,
            content_summary='test',
            detail={'error': error_detail} if not success else {},
            result_status='success' if success else 'failed',
            correlation_id=correlation_id,
        )

        if success:
            messages.success(request, "Test post succeeded.")
        else:
            messages.error(request, f"Test post failed: {error_detail}")

        return redirect('core:account_detail', pk=pk)

class AccountDeleteView(LoginRequiredMixin, DeleteView):
    model = PostingAccount
    template_name = 'accounts/delete_confirm.html'
    success_url = reverse_lazy('core:account_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['affected_schedules'] = check_account_dependencies(self.object)
        return context

    def form_valid(self, form):
        affected = check_account_dependencies(self.object)
        with transaction.atomic():
            if affected:
                cascade_cancel(affected, 'account_deleted')
            log_event(
                event_type='DEPENDENCY_DELETE_CONFIRMED',
                account=self.object,
                detail={'deleted': 'account', 'name': self.object.name},
                result_status='confirmed',
            )
            return super().form_valid(form)

from django.urls import reverse_lazy
from django.views.generic import FormView, CreateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

from core.models.notifications import SMTPSettings, NotificationRecipient
from core.forms.settings import SMTPSettingsForm, NotificationRecipientForm
from core.services.history import log_event
from core.services.encryption import decrypt

class SMTPSettingsView(LoginRequiredMixin, FormView):
    template_name = 'settings/smtp.html'
    form_class = SMTPSettingsForm
    success_url = reverse_lazy('core:smtp_settings')

    def get_object(self):
        return SMTPSettings.load()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.get_object()
        return kwargs

    def form_valid(self, form):
        password_changed = bool(form.cleaned_data.get('password'))
        form.save()
        messages.success(self.request, "SMTP settings updated successfully.")

        if password_changed:
            log_event('SMTP_SECRET_REPLACED', detail="SMTP password was updated.")

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['recipients'] = NotificationRecipient.objects.all().order_by('-created_at')
        ctx['recipient_form'] = NotificationRecipientForm()
        return ctx

class RecipientCreateView(LoginRequiredMixin, CreateView):
    model = NotificationRecipient
    form_class = NotificationRecipientForm
    success_url = reverse_lazy('core:smtp_settings')

    def form_valid(self, form):
        messages.success(self.request, "Recipient added successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"Error adding recipient: {error}")
        return redirect('core:smtp_settings')

class RecipientDeleteView(LoginRequiredMixin, DeleteView):
    model = NotificationRecipient
    success_url = reverse_lazy('core:smtp_settings')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Recipient removed successfully.")
        return super().delete(request, *args, **kwargs)

class TestEmailView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        settings_obj = SMTPSettings.load()
        recipients = list(NotificationRecipient.objects.values_list('email', flat=True))

        if not recipients:
            messages.error(request, "No recipients configured to receive the test email.")
            return redirect('core:smtp_settings')

        if not settings_obj.host or not settings_obj.sender_email:
            messages.error(request, "SMTP settings are incomplete. Please configure host and sender email.")
            return redirect('core:smtp_settings')

        try:
            password = decrypt(settings_obj.encrypted_password) if settings_obj.encrypted_password else ''
            backend = EmailBackend(
                host=settings_obj.host,
                port=settings_obj.port,
                username=settings_obj.username,
                password=password,
                use_tls=settings_obj.use_tls,
                fail_silently=False,
            )
            # EmailBackend in Django < 5 used use_tls, but for STARTTLS the parameter in Django 5 is use_tls (for explicit TLS/STARTTLS)
            # Actually Django 3+ uses use_tls (for STARTTLS) and use_ssl (for implicit TLS).
            # The model has use_tls and use_starttls.
            # Let's map model.use_tls to use_ssl, and model.use_starttls to use_tls.
            backend.use_ssl = settings_obj.use_tls
            backend.use_tls = settings_obj.use_starttls

            msg = EmailMessage(
                subject="Test Email from TwitterBot",
                body="This is a test email. Your SMTP configuration is working correctly.",
                from_email=settings_obj.sender_email,
                to=recipients,
                connection=backend,
            )
            msg.send()

            messages.success(request, f"Test email sent successfully to {len(recipients)} recipient(s).")
            log_event('TEST_POST_SUCCEEDED', detail="SMTP test email sent successfully.")
        except Exception as e:
            messages.error(request, f"Failed to send test email: {str(e)}")
            log_event('TEST_POST_FAILED', detail=f"SMTP test email failed: {str(e)}")

        return redirect('core:smtp_settings')

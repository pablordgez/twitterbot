import logging
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.models import User
from django.db import transaction, IntegrityError
from django.contrib.auth import login
from django.contrib.auth.views import LoginView as BaseLoginView

from core.services.history import log_event

logger = logging.getLogger(__name__)

class SetupView(View):
    def get(self, request):
        if User.objects.exists():
            return redirect('core:login')
        from core.forms.auth import SetupForm
        form = SetupForm()
        return render(request, 'auth/setup.html', {'form': form})

    def post(self, request):
        if User.objects.exists():
            return redirect('core:login')

        log_event('AUTH_SETUP_STARTED', detail={'username': request.POST.get('username', '')})
        
        from core.forms.auth import SetupForm
        form = SetupForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            try:
                with transaction.atomic():
                    if User.objects.count() > 0:
                        logger.warning("AUTH_SETUP_BLOCKED: Setup attempted but admin already exists.")
                        log_event('AUTH_SETUP_BLOCKED', detail={'reason': 'Setup attempted but admin already exists'})
                        return redirect('core:login')
                    
                    user = User.objects.create_superuser(username=username, email='', password=password)
                    logger.info("AUTH_SETUP_COMPLETED: First-run setup completed successfully.")
                    log_event('AUTH_SETUP_COMPLETED', detail={'username': username})
                    
                    # Log in after setup
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    return redirect('core:dashboard')
            except IntegrityError:
                logger.warning("AUTH_SETUP_BLOCKED: Setup transaction failed.")
                log_event('AUTH_SETUP_BLOCKED', detail={'reason': 'Setup transaction failed'})
                return redirect('core:login')
                
        return render(request, 'auth/setup.html', {'form': form})

class LoginView(BaseLoginView):
    template_name = 'auth/login.html'
    redirect_authenticated_user = True
    
    def form_valid(self, form):
        # auth_login automatically cycles the session key
        response = super().form_valid(form)
        logger.info(f"AUTH_LOGIN_SUCCESS: User {self.request.user.username} logged in.")
        log_event('AUTH_LOGIN_SUCCESS', detail={'username': self.request.user.username})
        return response

    def form_invalid(self, form):
        username = self.request.POST.get('username')
        logger.warning(f"AUTH_LOGIN_FAILURE: Failed login attempt for username '{username}'.")
        log_event('AUTH_LOGIN_FAILURE', detail={'username': username})
        return super().form_invalid(form)

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth.models import User

class FirstRunMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Exclude setup view, static files, and health check from redirection
        excluded_paths = [
            reverse('core:setup'),
            '/static/',
            reverse('health_check'),
        ]

        if not any(request.path.startswith(path) for path in excluded_paths):
            if not User.objects.exists():
                return redirect('core:setup')

        return self.get_response(request)

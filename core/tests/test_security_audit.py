import re
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings

class SecurityAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        
    def test_all_routes_require_auth(self):
        """Verify state-changing routes require auth."""
        routes_to_check = [
            'core:account_list',
            'core:account_create',
            'core:tweet_list_list',
            'core:tweet_list_create',
            'core:schedule_list',
            'core:schedule_create',
            'core:upcoming_list',
            'core:history_list',
            'core:smtp_settings',
        ]
        
        for route in routes_to_check:
            url = reverse(route)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"Route {route} did not redirect to login")
            self.assertIn('login', response.url.lower())

    def test_csrf_protection_on_forms(self):
        """Verify CSRF middleware is enabled in settings."""
        self.assertIn('django.middleware.csrf.CsrfViewMiddleware', settings.MIDDLEWARE)
        
    def test_session_cookie_flags(self):
        """Verify secure cookie flags are configured."""
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        
    def test_no_plaintext_secrets_in_logs(self):
        """Verify logging config doesn't expose secrets (basic check)."""
        # This is a structural test - we just verify history service masks secrets
        from core.services.history import log_event
        from core.models.history import HistoryEvent
        
        log_event('TEST_EVENT', detail={'password': 'secret_password_123', 'normal_field': 'value'})
        event = HistoryEvent.objects.last()
        self.assertNotIn('secret_password_123', str(event.detail))
        self.assertIn('password', str(event.detail))
        
    def test_import_curl_parser_no_shell(self):
        """Verify cURL parser doesn't use subprocess."""
        import ast
        import os
        from django.conf import settings
        
        parser_file = os.path.join(settings.BASE_DIR, 'core', 'services', 'curl_parser.py')
        with open(parser_file, 'r') as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                module_name = getattr(node, 'module', None)
                if module_name:
                    self.assertNotIn(module_name, ['subprocess', 'os', 'sys'])
                for alias in node.names:
                    self.assertNotIn(alias.name, ['subprocess', 'system', 'popen', 'run'])

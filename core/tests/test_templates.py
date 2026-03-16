from django.test import SimpleTestCase, RequestFactory
from django.template import Context, Template
from core.templatetags.ui_tags import schedule_type_badge, content_mode_badge, status_badge
from django.urls import reverse, resolve

class TemplateTagTests(SimpleTestCase):
    def test_schedule_type_badge(self):
        out = schedule_type_badge('one_time')
        self.assertIn('One-Time', out)
        
    def test_content_mode_badge(self):
        out = content_mode_badge('fixed_new')
        self.assertIn('Fixed (New)', out)
        self.assertIn('gray', out)
        
    def test_status_badge(self):
        out = status_badge('pending')
        self.assertIn('Pending', out)
        self.assertIn('yellow', out)

class BaseTemplateTest(SimpleTestCase):
    def test_base_render(self):
        # We need a request object to test base.html properly because of request.resolver_match
        request = RequestFactory().get('/')
        # Give it a dummy resolver_match to avoid errors in template
        request.resolver_match = type('ResolverMatch', (object,), {'url_name': 'dashboard'})()
        
        template = Template("{% extends 'base.html' %}")
        try:
            rendered = template.render(Context({'request': request}))
            self.assertIn('Twitter Bot', rendered)
            self.assertIn('Dashboard', rendered)
            self.assertIn('Accounts', rendered)
            self.assertIn('Tweet Lists', rendered)
        except Exception as e:
            self.fail(f"Template rendering failed: {e}")

from django import template
from django.utils.html import format_html

register = template.Library()

@register.simple_tag
def schedule_type_badge(schedule_type):
    if schedule_type == 'one_time':
        return format_html('<span class="badge bg-blue text-blue-fg">One-Time</span>')
    elif schedule_type == 'recurring':
        return format_html('<span class="badge bg-purple text-purple-fg">Recurring</span>')
    return format_html('<span class="badge">Unknown</span>')

@register.simple_tag
def content_mode_badge(content_mode):
    modes = {
        'fixed_new': ('Fixed (New)', 'gray'),
        'fixed_from_list': ('Fixed (From List)', 'gray'),
        'random_from_list': ('Random (From List)', 'azure'),
        'random_from_lists': ('Random (Multi-List)', 'azure'),
    }
    label, color = modes.get(content_mode, (content_mode, 'gray'))
    return format_html('<span class="badge bg-{0}-lt">{1}</span>', color, label)

@register.simple_tag
def status_badge(status):
    status_colors = {
        'pending': 'yellow',
        'executing': 'blue',
        'completed': 'green',
        'failed': 'red',
        'missed': 'orange',
        'skipped': 'gray',
        'canceled': 'red',
        'active': 'green',
    }
    color = status_colors.get(status, 'gray')
    return format_html('<span class="badge bg-{0} text-{0}-fg">{1}</span>', color, status.title())

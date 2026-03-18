from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from core.models.accounts import PostingAccount
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.models.history import HistoryEvent

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['account_count'] = PostingAccount.objects.count()
        context['active_schedule_count'] = Schedule.objects.filter(status='active').count()
        context['next_occurrence'] = Occurrence.objects.filter(
            status=Occurrence.Status.PENDING,
            due_at__gte=timezone.now()
        ).order_by('due_at').first()
        context['recent_events'] = HistoryEvent.objects.select_related('account', 'schedule').order_by('-timestamp')[:5]
        return context

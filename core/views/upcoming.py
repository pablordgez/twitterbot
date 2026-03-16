from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models.execution import Occurrence

class UpcomingListView(LoginRequiredMixin, ListView):
    model = Occurrence
    template_name = 'upcoming/list.html'
    paginate_by = 25
    
    def get_queryset(self):
        return Occurrence.objects.filter(
            status=Occurrence.Status.PENDING
        ).select_related('schedule').prefetch_related(
            'schedule__target_accounts__account', 
            'schedule__source_lists__tweet_list'
        ).order_by('due_at')

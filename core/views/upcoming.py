from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from core.models.execution import Occurrence
from core.models.history import HistoryEvent

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

class OccurrenceCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        occurrence = get_object_or_404(
            Occurrence.objects.filter(status=Occurrence.Status.PENDING), 
            pk=pk
        )
        
        occurrence.status = Occurrence.Status.CANCELED
        occurrence.cancel_reason = 'manual'
        occurrence.save()
        
        HistoryEvent.objects.create(
            event_type='SCHEDULE_CANCELED',
            schedule=occurrence.schedule,
            occurrence=occurrence,
            result_status='canceled',
            detail={'reason': 'manual_cancellation'}
        )
        
        messages.success(request, f"Occurrence #{occurrence.pk} for {occurrence.schedule.get_schedule_type_display()} schedule canceled.")
        return redirect('core:upcoming_list')

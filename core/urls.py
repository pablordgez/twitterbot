from django.urls import path
from django.contrib.auth.views import LogoutView
from .views.auth import SetupView, LoginView
from .views.dashboard import DashboardView
from .views.accounts import (
    AccountListView, AccountCreateView, AccountUpdateView,
    AccountDetailView, AccountDeleteView, AccountCurlImportView, AccountTestPostView
)
from .views.tweet_lists import (
    TweetListListView, TweetListCreateView, TweetListUpdateView, TweetListDeleteView, TweetListDetailView
)
from .views.tweet_entries import (
    TweetEntryCreateView, TweetEntryUpdateView, TweetEntryDeleteView
)
from .views.csv_import import CSVImportView
from .views.schedules import (
    ScheduleListView, ScheduleCreateView, ScheduleUpdateView,
    ScheduleDetailView, ScheduleCancelView,
    RecurringFieldsPartialView, ContentModePartialView,
)
from .views.upcoming import UpcomingListView
app_name = 'core'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('setup/', SetupView.as_view(), name='setup'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    
    path('accounts/', AccountListView.as_view(), name='account_list'),
    path('accounts/create/', AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/', AccountDetailView.as_view(), name='account_detail'),
    path('accounts/<int:pk>/edit/', AccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', AccountDeleteView.as_view(), name='account_delete'),
    path('accounts/<int:pk>/import/', AccountCurlImportView.as_view(), name='account_import'),
    path('accounts/<int:pk>/test_post/', AccountTestPostView.as_view(), name='account_test_post'),

    path('tweet-lists/', TweetListListView.as_view(), name='tweet_list_list'),
    path('tweet-lists/create/', TweetListCreateView.as_view(), name='tweet_list_create'),
    path('tweet-lists/<int:pk>/', TweetListDetailView.as_view(), name='tweet_list_detail'),
    path('tweet-lists/<int:pk>/edit/', TweetListUpdateView.as_view(), name='tweet_list_update'),
    path('tweet-lists/<int:pk>/delete/', TweetListDeleteView.as_view(), name='tweet_list_delete'),
    path('tweet-lists/<int:list_pk>/import/', CSVImportView.as_view(), name='csv_import'),
    path('tweet-lists/import/', CSVImportView.as_view(), name='csv_import_general'),

    path('tweet-lists/<int:list_pk>/entries/create/', TweetEntryCreateView.as_view(), name='tweet_entry_create'),
    path('tweet-entries/<int:pk>/edit/', TweetEntryUpdateView.as_view(), name='tweet_entry_update'),
    path('tweet-entries/<int:pk>/delete/', TweetEntryDeleteView.as_view(), name='tweet_entry_delete'),

    path('schedules/', ScheduleListView.as_view(), name='schedule_list'),
    path('schedules/create/', ScheduleCreateView.as_view(), name='schedule_create'),
    path('schedules/<int:pk>/', ScheduleDetailView.as_view(), name='schedule_detail'),
    path('schedules/<int:pk>/edit/', ScheduleUpdateView.as_view(), name='schedule_update'),
    path('schedules/<int:pk>/cancel/', ScheduleCancelView.as_view(), name='schedule_cancel'),
    path('schedules/partials/recurring-fields/', RecurringFieldsPartialView.as_view(), name='schedule_recurring_partial'),
    path('schedules/partials/content-mode/', ContentModePartialView.as_view(), name='schedule_content_mode_partial'),

    path('upcoming/', UpcomingListView.as_view(), name='upcoming_list'),
]

from django.urls import path
from django.contrib.auth.views import LogoutView
from .views.auth import SetupView, LoginView
from .views.dashboard import DashboardView
from .views.accounts import (
    AccountListView, AccountCreateView, AccountUpdateView,
    AccountDetailView, AccountDeleteView, AccountCurlImportView, AccountTestPostView
)

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
]

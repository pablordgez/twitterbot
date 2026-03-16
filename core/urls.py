from django.urls import path
from django.contrib.auth.views import LogoutView
from .views.auth import SetupView, LoginView
from .views.dashboard import DashboardView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('setup/', SetupView.as_view(), name='setup'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
]

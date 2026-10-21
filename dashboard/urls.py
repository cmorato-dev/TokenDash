from django.urls import path
from .views import DashboardView, EmbedView, HistoryView, RefreshView, SensorView, StatusView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('api/status/', StatusView.as_view(), name='provider-status'),
    path('api/history/', HistoryView.as_view(), name='usage-history'),
    path('api/refresh/<str:provider>/', RefreshView.as_view(), name='provider-refresh'),
    # Home Assistant: one page per module and one sensor endpoint per provider.
    path('ha/<str:module>/', EmbedView.as_view(), name='embed'),
    path('api/ha/<str:provider>/', SensorView.as_view(), name='ha-sensor'),
]

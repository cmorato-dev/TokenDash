from django.urls import path
from .views import DashboardView, EmbedView, HistoryView, RefreshView, SensorView, StatusView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    # Home Assistant: one page per module.
    path('ha/<str:module>/', EmbedView.as_view(), name='embed'),
]

# Outside the language prefix (see config/urls.py).
api_urlpatterns = [
    path('api/status/', StatusView.as_view(), name='provider-status'),
    path('api/history/', HistoryView.as_view(), name='usage-history'),
    path('api/refresh/<str:provider>/', RefreshView.as_view(), name='provider-refresh'),
    # Home Assistant: one sensor endpoint per provider.
    path('api/ha/<str:provider>/', SensorView.as_view(), name='ha-sensor'),
]

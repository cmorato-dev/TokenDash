from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from dashboard.accounts import FirstPasswordChangeView

urlpatterns = [
    path('admin/conectar/', include('scraper.urls')),
    # Address of the page before 21/10, kept for bookmarks.
    path('admin/scraper/scrapersession/connect/', RedirectView.as_view(pattern_name='scraper_connect', permanent=True)),
    path('admin/', admin.site.urls),
    path('accounts/password_change/', FirstPasswordChangeView.as_view(), name='password_change'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('dashboard.urls')),
]

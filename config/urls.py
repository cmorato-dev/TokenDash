from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog

from dashboard.accounts import FirstPasswordChangeView
from dashboard.urls import api_urlpatterns
from dashboard.views import EmbedView

# The JSON API keeps one address for every language: the dashboard and Home
# Assistant ask it with the language they want in Accept-Language.
urlpatterns = [
    *api_urlpatterns,
    # Home Assistant modules created before the /en/ and /es/ addresses: they keep
    # working in the language of the browser that shows them.
    path('ha/<str:module>/', EmbedView.as_view(), name='embed-legacy'),
    path('i18n/', include('django.conf.urls.i18n')),
]
# Every page has one address per language, /en/… and /es/…; an address without
# the prefix redirects to the visitor's language.
urlpatterns += i18n_patterns(
    path('admin/connect/', include('scraper.urls')),
    # Earlier addresses of the page, kept for bookmarks.
    path('admin/conectar/', RedirectView.as_view(pattern_name='scraper_connect', permanent=True)),
    path('admin/scraper/scrapersession/connect/', RedirectView.as_view(pattern_name='scraper_connect', permanent=True)),
    path('admin/', admin.site.urls),
    path('accounts/password_change/', FirstPasswordChangeView.as_view(), name='password_change'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    path('', include('dashboard.urls')),
)

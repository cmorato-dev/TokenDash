"""Superuser pages to connect the ChatGPT and Claude accounts, inside the admin."""
from django.contrib import admin
from django.urls import path

from .claude_client_views import claude_client_mode
from .codex_views import codex_login
from .connection_views import connections

urlpatterns = [
    path('', admin.site.admin_view(connections), name='scraper_connect'),
    path('codex/', admin.site.admin_view(codex_login), name='scraper_codex_login'),
    path('claude/', admin.site.admin_view(claude_client_mode), name='scraper_claude_client'),
]

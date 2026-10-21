from django.contrib import admin
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _('TokenDash · Administration')
admin.site.site_title = 'TokenDash'
admin.site.index_title = _('Administration')

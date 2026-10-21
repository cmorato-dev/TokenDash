from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from dashboard.accounts import DEFAULT_PASSWORD, DEFAULT_USERNAME


class Command(BaseCommand):
    help = 'Creates the initial administrator if there are no users yet. Their password must be changed at the first sign-in.'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists():
            self.stdout.write(_('There are already users: the initial administrator is not created.'))
            return
        User.objects.create_superuser(DEFAULT_USERNAME, '', DEFAULT_PASSWORD)
        self.stdout.write(self.style.SUCCESS(
            _('Initial administrator created. Username: %(username)s · Password: %(password)s. '
              'A new password will be asked for at the first sign-in.')
            % {'username': DEFAULT_USERNAME, 'password': DEFAULT_PASSWORD}))

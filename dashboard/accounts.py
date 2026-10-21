"""First sign-in of a new installation.

The first deployment creates the administrator ``admin`` with the password
``tokendash`` (``create_initial_admin``). Whoever signs in with that password is
sent to the password change page and cannot use anything else until they choose
a new one. Usernames, new users and later password changes are managed from the
administration panel.
"""
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _

DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'tokendash'
SESSION_FLAG = 'must_change_password'


@receiver(user_logged_in)
def flag_default_password(sender, request, user, **kwargs):
    # Checked once per sign-in, so it also catches a password set back to the default.
    if user.check_password(DEFAULT_PASSWORD):
        request.session[SESSION_FLAG] = True


class PasswordChangeRequiredMiddleware:
    """Keep a session that signed in with the default password on the change page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get(SESSION_FLAG) and request.user.is_authenticated:
            # The script catalog too: the change page shows its messages in the right language.
            allowed = {reverse('password_change'), reverse('logout'), reverse('admin:logout'), reverse('javascript-catalog')}
            if request.path not in allowed:
                if request.path.startswith('/api/'):
                    return JsonResponse({'error': _('Change the initial password to continue.')}, status=403)
                return redirect('password_change')
        return self.get_response(request)


class FirstPasswordChangeView(PasswordChangeView):
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.pop(SESSION_FLAG, None)
        return response

    def get_context_data(self, **kwargs):
        return super().get_context_data(forced=bool(self.request.session.get(SESSION_FLAG)), **kwargs)


class NotDefaultPasswordValidator:
    """The published default password can never be chosen again."""

    def validate(self, password, user=None):
        if password == DEFAULT_PASSWORD:
            raise ValidationError(_('You cannot use the initial TokenDash password.'), code='password_is_default')

    def get_help_text(self):
        return _('It cannot be the initial TokenDash password.')

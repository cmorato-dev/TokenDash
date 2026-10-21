from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from dashboard.accounts import DEFAULT_PASSWORD, DEFAULT_USERNAME


class Command(BaseCommand):
    help = 'Crea el administrador inicial si todavía no hay ningún usuario. Se pide cambiar su contraseña al entrar.'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists():
            self.stdout.write('Ya hay usuarios: no se crea el administrador inicial.')
            return
        User.objects.create_superuser(DEFAULT_USERNAME, '', DEFAULT_PASSWORD)
        self.stdout.write(self.style.SUCCESS(
            f'Administrador inicial creado. Usuario: {DEFAULT_USERNAME} · Contraseña: {DEFAULT_PASSWORD}. '
            'Al entrar se pedirá elegir una contraseña nueva.'))

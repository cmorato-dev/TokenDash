"""Create .env with random secrets, without printing them or overwriting an existing one.

    python3 scripts/init_env.py                  only this computer can open TokenDash
    python3 scripts/init_env.py 192.168.1.50     also the other devices of the network,
                                                 at http://192.168.1.50:8000
"""
from pathlib import Path
import ipaddress
import re
import secrets
import sys

root = Path(__file__).resolve().parent.parent
target = root / '.env'
address = sys.argv[1].strip() if len(sys.argv) > 1 else ''
if address:
    try:
        ipaddress.ip_address(address)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9.-]+', address):
            sys.exit(f'«{address}» no es una IP ni un nombre de equipo válido.')
if target.exists():
    print('.env ya existe; se conserva sin cambios.')
else:
    contents = (root / '.env.example').read_text(encoding='utf-8')
    contents = contents.replace('replace-with-a-long-random-secret', secrets.token_urlsafe(64))
    contents = contents.replace('replace-with-a-strong-database-password', secrets.token_urlsafe(32))
    if address:
        contents = contents.replace('DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1', f'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,{address}')
        contents = contents.replace('DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000',
                                    f'DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://{address}:8000')
        contents = contents.replace('# WEB_BIND=0.0.0.0', 'WEB_BIND=0.0.0.0')
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(contents)
    target.chmod(0o600)
    print('.env creado con secretos aleatorios.')
    if address:
        print(f'TokenDash se podrá abrir desde la red en http://{address}:8000')
    else:
        print('TokenDash se podrá abrir solo desde este equipo, en http://localhost:8000')

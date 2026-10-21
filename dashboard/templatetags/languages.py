"""The addresses of the current page in each language, for the hreflang links."""
from django import template
from django.conf import settings
from django.urls import translate_url

register = template.Library()


@register.simple_tag(takes_context=True)
def alternate_urls(context):
    """[(language, absolute URL)] for every language, plus ('x-default', the address without a prefix)."""
    request = context.get('request')
    if request is None:
        return []
    path = request.get_full_path()
    links = [(code, request.build_absolute_uri(translate_url(path, code))) for code, _name in settings.LANGUAGES]
    # Without the prefix, the server chooses the visitor's language.
    default = translate_url(path, settings.LANGUAGES[0][0]).removeprefix(f'/{settings.LANGUAGES[0][0]}')
    return links + [('x-default', request.build_absolute_uri(default or '/'))]

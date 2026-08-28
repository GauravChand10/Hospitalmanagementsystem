"""Content-versioned asset URLs so browsers do not reuse outdated styling."""
import hashlib
from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(path):
    url = static(path)
    source = finders.find(path)
    if not source:
        return url
    digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()[:12]
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={digest}"

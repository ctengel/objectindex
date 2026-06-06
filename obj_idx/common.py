"""Shared helpers used across the ObjectIndex API, client, and GUI.

Kept dependency-light (stdlib only) so any component can import it without
pulling in heavier modules such as ``client``/``clilib``.
"""

from urllib.parse import urlparse


def is_valid_url(url_string):
    """True if URL, False if not"""
    try:
        result = urlparse(url_string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

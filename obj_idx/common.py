"""Shared helpers used across the ObjectIndex API, client, and GUI.

Kept dependency-light (stdlib only) so any component can import it without
pulling in heavier modules such as ``client``/``clilib``.
"""

from urllib.parse import urlparse
import warnings
import mimetypes

def is_valid_url(url_string):
    """True if URL, False if not"""
    try:
        result = urlparse(url_string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def reconcile_mime_ext(filename, mime):
    if not mime:
        return filename, get_mime(filename)
    new_ext = mimetypes.guess_extension(mime, strict=False)
    if not filename:
        return f"{mime.partition('/')[0]}{new_ext or ''}", mime
    if not get_mime(filename):
        return f"{filename}{new_ext or ''}", mime
    if get_mime(filename) == mime:
        return filename, mime
    warnings.warn(f"File {filename} extension doesn't match MIME {mime}, appending {new_ext}")
    return f"{filename}{new_ext or ''}", mime

def get_mime(file_path: pathlib.Path) -> str:
    """Determine MIME type of a given path from extension"""
    if not file_path:
        return None
    return mimetypes.guess_type(file_path, strict=False)[0]

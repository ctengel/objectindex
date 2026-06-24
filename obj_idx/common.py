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

# The catch-all MIME libmagic returns when it can't identify the bytes. Some valid ISO-Media
# brands (e.g. f4v, mp71) sniff to this because the magic DB describes the ftyp box but has no
# MIME line for that brand, so we must not treat it as a contradiction of a concrete extension.
GENERIC_MIME = "application/octet-stream"

def reconcile_mime_ext(filename, mime):
    ext_mime = get_mime(filename)
    # A generic octet-stream sniff means "unknown content": trust a concrete extension type
    # rather than overriding it and tacking on .bin (e.g. a valid mp4 whose ISO brand libmagic
    # has no MIME line for).
    if mime == GENERIC_MIME and ext_mime:
        return filename, ext_mime
    if not mime:
        return filename, ext_mime
    new_ext = mimetypes.guess_extension(mime, strict=False)
    if not filename:
        return f"{mime.partition('/')[0]}{new_ext or ''}", mime
    if not ext_mime:
        return f"{filename}{new_ext or ''}", mime
    if ext_mime == mime:
        return filename, mime
    warnings.warn(f"File {filename} extension doesn't match MIME {mime}, appending {new_ext}")
    return f"{filename}{new_ext or ''}", mime

def get_mime(file_path: pathlib.Path) -> str:
    """Determine MIME type of a given path from extension"""
    if not file_path:
        return None
    return mimetypes.guess_type(file_path, strict=False)[0]

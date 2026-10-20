"""Fetch the Teams website's icon for a local shortcut; do not redistribute it."""
import hashlib
import struct
from urllib.request import urlopen

URL = ('https://teams.public.onecdn.static.microsoft/evergreen-assets/icons/'
       'microsoft_teams_logo_refresh_v2025.ico')
SHA256 = '5b47b12308f87a6a8060f63dc91ca2fd01b063e3d233aa62f5ec255cd68e6037'
LIMIT = 512 * 1024
PNG = b'\x89PNG\r\n\x1a\n'


def extract_png(raw):
    """Extract an existing PNG from ICO without changing any artwork pixels."""
    if len(raw) < 6:
        raise ValueError('Invalid icon header')
    reserved, kind, count = struct.unpack_from('<HHH', raw)
    if reserved or kind != 1 or not 1 <= count <= 64 or len(raw) < 6 + count * 16:
        raise ValueError('Invalid icon directory')
    images = []
    for index in range(count):
        width, height, _, _, _, _, size, offset = struct.unpack_from('<BBBBHHII', raw, 6 + index * 16)
        if offset < 6 + count * 16 or offset + size > len(raw):
            raise ValueError('Invalid icon image bounds')
        content = raw[offset:offset + size]
        if content.startswith(PNG):
            images.append(((width or 256) * (height or 256), content))
    if not images:
        raise ValueError('The icon contains no PNG image')
    return max(images, key=lambda item: item[0])[1]


def download():
    with urlopen(URL, timeout=15) as response:
        # Require Microsoft's HTTPS origin even if the asset starts redirecting.
        if response.url != URL:
            raise ValueError('Unexpected icon redirect')
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT or hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('The upstream icon changed; review its new checksum before updating')
    return extract_png(raw)

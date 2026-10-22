"""Resource-bounded image decoder. stdin only; fixed statuses; never render SVG."""
import io
import math
import os
import re
import resource
import sys
import warnings
from importlib.metadata import version

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
PINS = {'Pillow': '12.3.0', 'pillow-heif': '1.8.1', 'defusedxml': '0.7.1'}


class Invalid(Exception):
    def __init__(self, code):
        self.code = code


def dimensions(width, height):
    if not all(math.isfinite(v) and v > 0 for v in (width, height)) or width * height > MAX_PIXELS:
        raise Invalid(6)


def svg(data):
    from defusedxml import ElementTree as ET
    # Explicit UTF-8 keeps XML encodings from bypassing the text scanner.
    data.decode('utf-8')
    root = ET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    namespace = '{http://www.w3.org/2000/svg}'
    if root.tag != namespace + 'svg':
        raise Invalid(7)
    tags = {'svg', 'g', 'defs', 'title', 'desc', 'metadata', 'path', 'rect', 'circle',
            'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'textPath',
            'use', 'symbol', 'clipPath', 'mask', 'linearGradient', 'radialGradient',
            'stop', 'marker', 'pattern'}
    attrs = set(('id class x y x1 y1 x2 y2 cx cy r rx ry width height viewBox '
                 'preserveAspectRatio d points transform fill fill-opacity fill-rule '
                 'stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin '
                 'stroke-dasharray stroke-dashoffset stroke-miterlimit opacity '
                 'font-family font-size font-weight font-style text-anchor '
                 'dominant-baseline dx dy rotate offset stop-color stop-opacity '
                 'gradientUnits gradientTransform spreadMethod fx fy '
                 'clip-path clip-rule mask marker-start marker-mid marker-end '
                 'markerWidth markerHeight markerUnits refX refY orient '
                 'patternUnits patternContentUnits patternTransform href version').split())
    queue = [(root, 1)]
    count = 0
    while queue:
        element, depth = queue.pop()
        count += 1
        if count > 10000 or depth > 64 or element.tag not in {namespace + tag for tag in tags}:
            raise Invalid(7)
        for name, value in element.attrib.items():
            if name in ('{http://www.w3.org/1999/xlink}href', '{http://www.w3.org/XML/1998/namespace}space'):
                name = 'href' if name.endswith('href') else 'xml-space'
            if name not in attrs | {'xml-space'} or len(value) > 65536:
                raise Invalid(7)
            if name == 'href' and not re.fullmatch(r'#[A-Za-z_][\w.:-]*', value):
                raise Invalid(7)
            # No CSS escapes, external URLs, data URIs, scripting or imports.
            if '\\' in value or re.search(r'(?i)(?:https?:|file:|data:|javascript:|@import)', value):
                raise Invalid(7)
            if 'url' in value.lower() and not re.fullmatch(r'url\(#[A-Za-z_][\w.:-]*\)', value):
                raise Invalid(7)
        queue.extend((child, depth + 1) for child in element)
    def length(value):
        if not re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)(?:px)?', value):
            raise Invalid(7)
        return float(value.removesuffix('px'))
    if 'width' in root.attrib and 'height' in root.attrib:
        dimensions(length(root.attrib['width']), length(root.attrib['height']))
    elif 'viewBox' not in root.attrib:
        raise Invalid(7)
    if 'viewBox' in root.attrib:
        box = [float(v) for v in re.split(r'[\s,]+', root.attrib['viewBox'].strip())]
        if len(box) != 4 or not all(math.isfinite(v) for v in box):
            raise Invalid(7)
        dimensions(box[2], box[3])
    # Processing instructions may direct a viewer to an external stylesheet.
    if re.search(rb'<\?(?!xml\s)', data):
        raise Invalid(7)


def raster(kind, data):
    from PIL import Image, ImageFile
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    if kind == 'HEIF':
        import pillow_heif
        pillow_heif.options.DECODE_THREADS = 1
        if pillow_heif.get_file_mimetype(data) != 'image/heic':
            raise Invalid(4)
        # Inspect the container without dropping auxiliary/depth/thumbnail data.
        heif = pillow_heif.open_heif(io.BytesIO(data))
        if len(heif) != 1 or data[8:12] in (b'hevc', b'hevx', b'msf1'):
            raise Invalid(5)
        if any(heif.info.get(key) for key in ('thumbnails', 'depth_images', 'aux')):
            raise Invalid(5)
        dimensions(*heif.size)
        heif[0].load()
        return
    with Image.open(io.BytesIO(data), formats=[kind]) as image:
        if image.format != kind:
            raise Invalid(4)
        dimensions(*image.size)
        if (getattr(image, 'n_frames', 1) != 1 or getattr(image, 'is_animated', False)
                or (kind == 'PNG' and 'loop' in image.info)):
            raise Invalid(5)
        image.verify()
    with Image.open(io.BytesIO(data), formats=[kind]) as image:
        image.load()


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    # Suppress native library diagnostics too, not just Python exceptions.
    with open(os.devnull, 'wb') as null:
        os.dup2(null.fileno(), 2)
    try:
        if any(version(name) != expected for name, expected in PINS.items()):
            return 3
        from PIL import Image, features
        import pillow_heif
        Image.init()
        if (not all(features.check(name) for name in ('jpg', 'zlib', 'libtiff', 'webp'))
                or not {'PNG', 'JPEG', 'WEBP', 'BMP', 'GIF', 'TIFF'} <= Image.OPEN.keys()
                or pillow_heif.libheif_version() != '1.23.6'
                or 'libde265' not in pillow_heif.libheif_info()['decoders']):
            return 3
    except Exception:
        return 3
    if sys.argv[1:] == ['--check']:
        print('VALID')
        return 0
    try:
        kind, = sys.argv[1:]
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            return 4
        if kind == 'SVG':
            svg(data)
        elif kind in ('PNG', 'JPEG', 'WEBP', 'BMP', 'GIF', 'TIFF', 'HEIF'):
            raster(kind, data)
        else:
            return 4
        sys.stdout.write('VALID\n')
        return 0
    except Invalid as error:
        return error.code
    except Exception as error:
        if type(error).__name__ in ('DecompressionBombWarning', 'DecompressionBombError'):
            return 6
        return 4


if __name__ == '__main__':
    raise SystemExit(main())

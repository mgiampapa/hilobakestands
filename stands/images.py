"""Image processing for owner photo uploads.

Everything runs on the (1 GB) Oracle box, so the rules are: cap the input,
process one image at a time, and re-encode everything. Re-encoding to a
fresh JPEG also strips ALL metadata — including EXIF GPS, which matters
because bakers photograph stands at their homes.
"""
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # refuse anything bigger up front
MAX_DIMENSION = 1600                  # gallery photos resized to fit this
MIN_DIMENSION = 200                   # reject postage stamps
THUMB_SIZE = (200, 200)               # list thumbnail (displayed ~100px, 2x)
Image.MAX_IMAGE_PIXELS = 40_000_000   # decompression-bomb guard (Pillow warns at default)


def process_upload(uploaded_file):
    """Validate + normalize an uploaded image.

    Returns (ContentFile of JPEG bytes, suggested_filename). Raises
    ValidationError with a friendly message for anything unusable.
    """
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValidationError(_('That photo is over 10 MB — please resize '
                                'it or pick a smaller one.'))
    try:
        img = Image.open(uploaded_file)
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(_("That file doesn't look like a photo we "
                                'can read (JPEG, PNG, WebP, or HEIC-free '
                                'formats work best).'))
    if min(img.size) < MIN_DIMENSION:
        raise ValidationError(_('That photo is too small — at least '
                                '200×200 pixels, please.'))

    img = ImageOps.exif_transpose(img)        # honor rotation, then drop EXIF
    if img.mode not in ('RGB',):              # flatten alpha/palette/CMYK
        img = img.convert('RGB')
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85, optimize=True)  # fresh file = no metadata
    return ContentFile(buf.getvalue()), 'photo.jpg'


def make_list_thumb(photo_field):
    """Square-crop thumbnail from a stored gallery photo."""
    photo_field.open('rb')
    try:
        img = Image.open(photo_field)
        img.load()
    finally:
        photo_field.close()
    if img.mode not in ('RGB',):
        img = img.convert('RGB')
    img = ImageOps.fit(img, THUMB_SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=80, optimize=True)
    return ContentFile(buf.getvalue()), 'thumb.jpg'

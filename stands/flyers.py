"""Claim-flyer PDFs: one US-letter page per stand with a QR claim link.

Matthew hands these out in person (or sends the plain URL by SMS/email).
Build with build_flyer_pdf(stands) -> bytes; every stand must already have
a claim_token.
"""
import io
import os

import qrcode
from django.conf import settings
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

GREEN = HexColor('#2e7d5b')
CORAL = HexColor('#e76f51')
SAND = HexColor('#fdf6ec')
INK = HexColor('#2b2b2b')
MUTED = HexColor('#777777')

_DEJAVU_DIR = '/usr/share/fonts/truetype/dejavu'
# Twemoji 1f33a (hibiscus), CC-BY 4.0 © Twitter — rasterized at 512px,
# committed as a static asset so prod needs no emoji fonts.
_FLOWER_PNG = os.path.join(os.path.dirname(__file__),
                           'static', 'stands', 'hibiscus.png')


def _fonts():
    """Register DejaVu (has the ʻokina glyph); fall back to Helvetica."""
    if os.path.exists(os.path.join(_DEJAVU_DIR, 'DejaVuSans.ttf')):
        if 'Flyer' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont('Flyer', os.path.join(_DEJAVU_DIR, 'DejaVuSans.ttf')))
            pdfmetrics.registerFont(
                TTFont('Flyer-Bold',
                       os.path.join(_DEJAVU_DIR, 'DejaVuSans-Bold.ttf')))
        return 'Flyer', 'Flyer-Bold'
    return 'Helvetica', 'Helvetica-Bold'


def _qr_image(url):
    qr = qrcode.QRCode(box_size=12, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color='#2b2b2b', back_color='white').get_image()


def _shrink_to_fit(c, text, font, size, max_width):
    while size > 14 and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _draw_page(c, stand, claim_url, fonts):
    font, bold = fonts
    w, h = letter

    # Header band: hibiscus + wordmark, centered as a unit (like the site)
    band = 1.1 * inch
    c.setFillColor(GREEN)
    c.rect(0, h - band, w, band, fill=1, stroke=0)
    title = 'HiloBakeStands.com'
    c.setFont(bold, 26)
    flower = 0.8 * inch  # proportional to the band, like the site header
    gap = 0.16 * inch
    total = flower + gap + c.stringWidth(title, bold, 26)
    x = (w - total) / 2
    band_mid = h - band / 2
    if os.path.exists(_FLOWER_PNG):
        c.drawImage(ImageReader(_FLOWER_PNG), x, band_mid - flower / 2,
                    flower, flower, mask='auto')
        x += flower + gap
    c.setFillColor(SAND)
    # optically center 26pt text on the band midline (cap height ≈ 0.7em)
    c.drawString(x, band_mid - 26 * 0.36, title)

    y = h - 1.85 * inch
    c.setFillColor(INK)
    c.setFont(bold, 20)
    c.drawCentredString(w / 2, y, 'Aloha! Is this your stand?')

    # Stand name, shrunk to fit
    y -= 0.75 * inch
    size = _shrink_to_fit(c, stand.name, bold, 34, w - 1.5 * inch)
    c.setFillColor(CORAL)
    c.setFont(bold, size)
    c.drawCentredString(w / 2, y, stand.name)

    # Pitch
    y -= 0.6 * inch
    c.setFillColor(INK)
    c.setFont(font, 13)
    for line in (
            'Your stand is listed on HiloBakeStands.com — a free community',
            'directory of Hilo bake stands, food trucks, farm stands & pop-ups.',
            '',
            'Scan the code to claim your listing. You sign in with Google and',
            'it takes about a minute. Once claimed, you can update your hours,',
            'flip an open/closed-today switch, add photos, and place your map pin.'):
        c.drawCentredString(w / 2, y, line)
        y -= 0.27 * inch

    # QR code
    qr_side = 3.2 * inch
    qr_y = y - qr_side - 0.15 * inch
    c.drawImage(ImageReader(_qr_image(claim_url)),
                (w - qr_side) / 2, qr_y, qr_side, qr_side)

    # Plain URL under the QR (works typed-out, or sent by SMS/email)
    c.setFont(font, 11)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, qr_y - 0.3 * inch, claim_url)
    c.setFont(font, 10)
    c.drawCentredString(w / 2, qr_y - 0.55 * inch,
                        'This link is just for your stand and works once.')

    # Footer band
    c.setFillColor(SAND)
    c.rect(0, 0, w, 0.95 * inch, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont(font, 11)
    c.drawCentredString(w / 2, 0.58 * inch,
                        'Questions? Email matt@hilobakestands.com')
    c.setFillColor(MUTED)
    c.setFont(font, 9)
    c.drawCentredString(w / 2, 0.32 * inch,
                        'Not-for-profit, made with aloha in Hilo. '
                        'No fees, no ads — just helping neighbors find you.')


def build_flyer_pdf(stands):
    """Return PDF bytes, one page per stand. Stands need claim_token set."""
    fonts = _fonts()
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=letter)
    c.setTitle('HiloBakeStands claim flyers')
    for stand in stands:
        claim_url = settings.SITE_BASE_URL + stand.claim_url_path
        _draw_page(c, stand, claim_url, fonts)
        c.showPage()
    c.save()
    return buf.getvalue()

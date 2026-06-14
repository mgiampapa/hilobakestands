"""Text moderation — first (cheap, always-on) layer of the TextModerator.

Screens submitter free text (name, description, address) for threats and
denylisted terms. The semantic LLM layer (pono/kind/constructive — SPEC-1.1
§5a, Cloudflare-Worker-primary / homelab-fallback) is deferred/stubbed; this
denylist is what ships in v1.1.

Two parts:
  * THREAT regex — built-in, catches violent/threat phrasing (the demonstrated
    gap: a death threat accepted in the address field during testing).
  * Word list — maintained OUT of source in data/denylist.txt (seed from a
    public profanity list + local Hawaiian Pidgin per §10.3; one term per line,
    blanks and #comments ignored). Kept narrow so legitimate Hawaiian/Pidgin
    content isn't flagged. Absent file = threat patterns only.
"""
import re
from pathlib import Path

_THREAT = re.compile(
    r"\b(?:kill|murder|shoot|stab|behead|rape|lynch|strangle)\s+"
    r"(?:you|him|her|them|u|ya|y'?all)\b"
    r"|\bi(?:'?m| am)?\s*(?:'?ll|will|gonna|going to)\s+"
    r"(?:kill|hurt|murder|shoot|stab|end)\b"
    r"|\bdeath\s+to\b",
    re.IGNORECASE,
)

_WORDLIST_PATH = Path(__file__).resolve().parent / 'data' / 'denylist.txt'


def _load_terms():
    try:
        lines = _WORDLIST_PATH.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return [t.strip().lower() for t in lines
            if t.strip() and not t.lstrip().startswith('#')]


# Loaded once at import; a deploy restart picks up wordlist edits.
_TERMS = _load_terms()


def text_blocked(*texts):
    """True if any of the given strings contains a threat phrase or a
    denylisted term. Used by the submit/owner forms to reject before saving."""
    blob = ' '.join(t for t in texts if t)
    if not blob.strip():
        return False
    if _THREAT.search(blob):
        return True
    low = blob.lower()
    return any(term in low for term in _TERMS)

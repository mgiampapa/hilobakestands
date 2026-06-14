"""Summarise the privacy-preserving usage log (USAGE_LOG_PATH).

Reads the append-only JSONL written by stands.middleware.UsageLogMiddleware
and prints basic stats, with the visitor language breakdown front and
centre — that's the signal for deciding whether Japanese i18n is worth it.

    python manage.py usage_stats
    python manage.py usage_stats --since 2026-06-01 --top 15
    python manage.py usage_stats --file /opt/hilobakestands/data/usage.jsonl

Heavier analysis can happen off-box; this is the quick on-box read.
"""
import json
from collections import Counter, defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _primary_lang(accept_language):
    """First language tag's base subtag, e.g. 'ja,en-US;q=0.9' -> 'ja'."""
    first = accept_language.split(',')[0].strip()
    tag = first.split(';')[0].strip()       # drop the q-value
    base = tag.split('-')[0].strip().lower()  # 'en-US' -> 'en'
    return base or '(none)'


class Command(BaseCommand):
    help = 'Summarise the usage log (counts, top paths, visitor languages).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=getattr(
            settings, 'USAGE_LOG_PATH', None),
            help='Path to the JSONL log (default: settings.USAGE_LOG_PATH).')
        parser.add_argument('--since', default=None,
                            help='Only rows on/after this UTC date (YYYY-MM-DD).')
        parser.add_argument('--top', type=int, default=10,
                            help='How many rows in each top-N list.')

    def handle(self, *args, **opts):
        path = opts['file']
        if not path:
            raise CommandError('No log file set (USAGE_LOG_PATH unset).')
        since = opts['since']
        top = opts['top']

        total = 0
        visitors, langs, paths, statuses = Counter(), Counter(), Counter(), Counter()
        per_day = defaultdict(lambda: {'req': 0, 'vis': set()})
        first_ts = last_ts = None
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = rec.get('ts', '')
                    if since and ts[:10] < since:
                        continue
                    total += 1
                    first_ts = first_ts or ts
                    last_ts = ts
                    day = ts[:10]
                    per_day[day]['req'] += 1
                    if rec.get('visitor'):
                        visitors[rec['visitor']] += 1
                        per_day[day]['vis'].add(rec['visitor'])
                    langs[_primary_lang(rec.get('lang', ''))] += 1
                    paths[rec.get('path', '?')] += 1
                    statuses[str(rec.get('status', '?'))] += 1
        except FileNotFoundError:
            raise CommandError(f'Log file not found: {path}')

        if not total:
            self.stdout.write('No matching log rows yet.')
            return

        w = self.stdout.write
        w(f'Usage log: {path}')
        w(f'Window:    {first_ts} -> {last_ts}'
          + (f'  (since {since})' if since else ''))
        w(f'Requests:  {total}')
        w(f'Visitors:  {len(visitors)}  (distinct daily-rotating hashes; '
          'unique-visitor-days, not lifetime uniques)')

        w('\nPer day (UTC):')
        w(f'  {"date":<10} {"requests":>9} {"visitors":>9}')
        for day in sorted(per_day):
            d = per_day[day]
            w(f'  {day:<10} {d["req"]:>9} {len(d["vis"]):>9}')

        w('\nVisitor language (primary Accept-Language) - the i18n signal:')
        for lang, n in langs.most_common(top):
            w(f'  {lang:<8} {n:>6}  {n / total:6.1%}')

        w('\nTop paths:')
        for p, n in paths.most_common(top):
            w(f'  {n:>6}  {p}')

        w('\nStatus codes:')
        for s, n in sorted(statuses.items()):
            w(f'  {s}: {n}')

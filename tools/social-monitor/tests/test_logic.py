"""Offline checks for the monitor's decision logic — no network, no email.

Run:  python3 tests/test_logic.py
Exercises the state machine through a fake fetcher + in-memory sqlite so we can
prove the two real guarantees: no false signal on first sight, and one-shot
signals on genuine active<->quiet crossings.
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import monitor  # noqa: E402

DAY = 86400
NOW = 1_750_000_000          # fixed "now" so tests are deterministic


def fresh_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(monitor.SCHEMA)
    return conn


def make_fetcher(result):
    """A fetcher that always returns the same ('kind', value) tuple."""
    return lambda handle: result


STAND = {'slug': 's1', 'name': 'Test Stand', 'instagram': 'teststand',
         'detail_url': 'https://example/s1'}

results = []
def check(name, cond):
    results.append((name, cond))
    print(('PASS' if cond else 'FAIL'), name)


def quiet_run(conn, fetcher, now):
    return monitor.run_pass([STAND], conn, fetcher, now, delay=False, log=lambda *a: None)


# 1. classify() boundaries
check('recent post -> active', monitor.classify(NOW - 5 * DAY, NOW) == 'active')
check('29 days -> active', monitor.classify(NOW - 29 * DAY, NOW) == 'active')
check('31 days -> quiet', monitor.classify(NOW - 31 * DAY, NOW) == 'quiet')
check('no posts -> quiet', monitor.classify(None, NOW) == 'quiet')

# 2. decide() transitions
check('first sight -> no signal', monitor.decide(None, 'quiet') is None)
check('unknown -> no signal', monitor.decide('unknown', 'active') is None)
check('active->quiet -> went_quiet', monitor.decide('active', 'quiet') == 'went_quiet')
check('quiet->active -> resumed', monitor.decide('quiet', 'active') == 'resumed')
check('active->active -> none', monitor.decide('active', 'active') is None)

# 3. First run on an active stand emits NOTHING (baseline only)
conn = fresh_conn()
d = quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW)
check('first run: no email', not any(d.values()))
check('first run: state stored active', monitor.get_row(conn, 's1')['state'] == 'active')

# 4. Active stand goes 40 days without posting -> went_quiet, once
d = quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW + 40 * DAY)
#    last post still 2-days-before-NOW, but evaluated 40 days later -> 42 days old
check('crossing 30d: went_quiet fires', len(d['went_quiet']) == 1 and not d['resumed'])
#    run again next day, still quiet -> must NOT re-fire
d = quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW + 41 * DAY)
check('still quiet: no repeat', not any(d.values()))

# 5. Quiet stand posts again -> resumed, once
d = quiet_run(conn, make_fetcher(('ok', NOW + 41 * DAY)), NOW + 41 * DAY)
check('new post: resumed fires', len(d['resumed']) == 1 and not d['went_quiet'])

# 6. A transient fetch error never flips an active stand to quiet / no false alarm
conn = fresh_conn()
quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW)          # baseline active
d = quiet_run(conn, make_fetcher(('error', 'rate limited (429)')), NOW + DAY)
check('1 error: no signal', not any(d.values()))
check('1 error: state still active', monitor.get_row(conn, 's1')['state'] == 'active')

# 7. Persistent errors (>= threshold) surface once as needs_check
conn = fresh_conn()
f_err = make_fetcher(('notfound', 'profile not found'))
for i in range(monitor.ERROR_THRESHOLD - 1):
    d = quiet_run(conn, f_err, NOW + i * DAY)
    assert not d['needs_check'], 'flagged too early'
d = quiet_run(conn, f_err, NOW + monitor.ERROR_THRESHOLD * DAY)
check('threshold reached: needs_check once', len(d['needs_check']) == 1)
d = quiet_run(conn, f_err, NOW + (monitor.ERROR_THRESHOLD + 1) * DAY)
check('past threshold: no repeat', not d['needs_check'])

# 8. Private account: recorded, never signalled
conn = fresh_conn()
d = quiet_run(conn, make_fetcher(('private', None)), NOW)
check('private: no signal', not any(d.values()))
check('private: state unknown', monitor.get_row(conn, 's1')['state'] == 'unknown')

# 9. Digest renders without error when populated
conn = fresh_conn()
quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW)
d = quiet_run(conn, make_fetcher(('ok', NOW - 2 * DAY)), NOW + 40 * DAY)
subj, body = monitor.render_digest(d, NOW + 40 * DAY)
check('digest renders subject', 'quiet' in subj.lower())
check('digest renders body', 'Test Stand' in body)

failed = [n for n, ok in results if not ok]
print(f'\n{len(results) - len(failed)}/{len(results)} passed')
sys.exit(1 if failed else 0)

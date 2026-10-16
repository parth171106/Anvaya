"""Bounded, account-scoped incident snapshots and self-contained PDF reports."""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import time
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

MAX_EVENTS = 200
FONT_DIR = Path(reportlab.__file__).parent / 'fonts'
for name, filename in [('Report', 'Vera.ttf'), ('ReportBold', 'VeraBd.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))


def stamp(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except (ValueError, TypeError, OverflowError, OSError):
        return 'Time unavailable'


def snapshot(c, incident_id, verify=True):
    """Run on the container's owning thread; PDF layout only runs in a worker."""
    detail = c.correlator.detail(incident_id)
    if detail is None:
        raise KeyError(incident_id)
    ids = list(dict.fromkeys(e['event_id'] for e in c.repo.incident_events(incident_id)))
    events = c.repo.summaries(ids[:MAX_EVENTS])
    events.sort(key=lambda e: (e['time'], e['seq'], e['event_id']))
    event_total = max(detail['event_count'], len(ids))
    checks = {}
    started = int(time.time() * 1000)
    for event in events:
        raw_id = event['raw_id']
        if raw_id in checks:
            continue
        check = {'status': 'NOT CHECKED', 'reason': 'Verification not requested.'}
        if verify:
            try:
                proof = c.ledger.verify_record(raw_id)
                if proof is None:
                    check['reason'] = 'Record is not sealed yet.'
                else:
                    checks_ok = {
                        'SHA-256': proof['sha256_stored'] == proof['sha256_now'],
                        'Merkle inclusion': proof['root_ok'],
                        'Ed25519 batch signature': proof['signature_ok'],
                        'Configured witness heads': all(w['agree'] for w in proof['witnesses']),
                    }
                    failed = [name for name, ok in checks_ok.items() if not ok]
                    check = {'status': 'FAILED' if failed else 'VERIFIED',
                             'reason': 'Failed: ' + ', '.join(failed) if failed else 'All listed record checks passed.',
                             'batch_id': proof['batch_id'], 'stored_hash': proof['sha256_stored'],
                             'current_hash': proof['sha256_now'], 'checks': checks_ok,
                             'witness_count': len(proof['witnesses'])}
            except (KeyError, OSError, ValueError, IndexError, TypeError):
                check['reason'] = 'Evidence or proof unavailable; verification could not complete.'
        checks[raw_id] = check
    counts = Counter(check['status'] for check in checks.values())
    status = ('FAILED' if counts['FAILED'] else 'NOT CHECKED'
              if not checks or counts['NOT CHECKED'] or event_total > len(events) else 'VERIFIED')
    activity = c.repo.incident_activity(incident_id)
    activity_total = c.repo.con.execute('SELECT COUNT(*) FROM incident_activity WHERE incident_id=?',
                                      (incident_id,)).fetchone()[0]
    return {'incident': detail, 'events': events, 'checks': checks, 'counts': counts, 'status': status,
            'event_total': event_total, 'omitted': event_total - len(events), 'activity': activity,
            'activity_total': activity_total, 'started_at': started, 'generated_at': int(time.time() * 1000),
            'demo_mode': c.cfg.demo_mode, 'primary_fingerprint': c.ledger.fp}


def render_pdf(data):
    """Only plain text enters Paragraph; no links, markup, or remote resources from logs."""
    buf = BytesIO()
    ink, muted, accent = colors.HexColor('#102536'), colors.HexColor('#506374'), colors.HexColor('#9b3c20')
    styles = {
        'body': ParagraphStyle('body', fontName='Report', fontSize=9, leading=13, textColor=ink, spaceAfter=6,
                               splitLongWords=True),
        'small': ParagraphStyle('small', fontName='Report', fontSize=7.5, leading=11, textColor=muted, spaceAfter=4),
        'title': ParagraphStyle('title', fontName='ReportBold', fontSize=23, leading=29, textColor=ink, spaceAfter=16),
        'h': ParagraphStyle('h', fontName='ReportBold', fontSize=13, leading=18, textColor=accent, spaceBefore=13,
                            spaceAfter=8, keepWithNext=True),
        'label': ParagraphStyle('label', fontName='ReportBold', fontSize=9, leading=13, textColor=ink,
                                spaceAfter=5, keepWithNext=True),
    }
    glyphs = pdfmetrics.getFont('Report').face.charToGlyph

    def p(value, style='body'):
        text = str(value if value is not None else 'Not recorded')
        text = text.translate(str.maketrans({'→': ' -> ', '–': '-', '—': '-', '…': '...'}))
        # Unsupported glyphs remain unambiguous instead of disappearing as black squares.
        text = ''.join(ch if ch in '\n\t' or ord(ch) in glyphs else f'[U+{ord(ch):04X}]' for ch in text)
        return Paragraph(escape(text).replace('\n', '<br/>'), styles[style])

    story = []
    def add(value, style='body'):
        story.append(p(value, style))

    d = data['incident']
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=48, bottomMargin=48,
                            title=f"ANVAYA incident report {d['incident_id']}", author='ANVAYA')
    add('ANVAYA / INCIDENT REPORT', 'h')
    add(d['title'], 'title')
    add(f"{d['incident_id']}  |  Generated {stamp(data['generated_at'])}", 'small')
    workflow = d.get('workflow', {})
    rows = [('Severity / review priority', f"{d['level']} / {d['risk']}/100"),
            ('Investigation', workflow.get('state', 'new').capitalize()),
            ('Event window', f"{stamp(d['first_time'])}\n{stamp(d['last_time'])}"),
            ('Source / target', f"{d['attacker_ip']} / {d.get('target_ip') or 'Not recorded'}"),
            ('Report coverage', f"{len(data['events'])} of {data['event_total']} linked events; {data['omitted']} omitted"),
            ('Raw-record integrity', data['status'])]
    table = Table([[p(k, 'label'), p(v)] for k, v in rows], colWidths=[155, 356], hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f4f5')),
                               ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                               ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story.append(table)
    add('Context and scope', 'h')
    labels = []
    if data['demo_mode']:
        labels.append('DEMO MODE')
    if workflow.get('controlled_test'):
        labels.append('CONTROLLED TEST (analyst annotation)')
    if any(str(name).lower().startswith('synthetic-lab-') for name in d['devices']):
        labels.append('SYNTHETIC-LABELLED SOURCE (device naming)')
    add('; '.join(labels) if labels else 'No controlled-test or synthetic-source label recorded. This does not establish a real attack.')
    add('A detection is a finding for review, not proof of compromise. Risk is a review priority, not a breach probability. '
        'This report is a point-in-time snapshot; the incident may change after export. No AI-generated explanation is included.')
    add('Why this needs attention', 'h')
    add(d.get('explanation') or 'No rule explanation recorded.')
    add(d.get('recommended_action') or 'Review the linked evidence and investigation notes.')
    story.append(PageBreak())
    add('Integrity and limitations', 'title')
    counts = data['counts']
    add(f"{data['status']} - {counts['VERIFIED']} verified / {counts['FAILED']} failed / "
        f"{counts['NOT CHECKED']} not checked (unique included raw records).", 'label')
    add(f"Check window: {stamp(data['started_at'])} to {stamp(data['generated_at'])}.")
    add('Fresh record checks compare current raw bytes to stored SHA-256, test Merkle inclusion, validate the signed '
        'batch head using Ed25519, and compare configured witness heads. They do not verify normalized fields, '
        'prove the source was truthful, verify the full chain history, or digitally sign this PDF. '
        'Witness stores are local to this deployment, not independent external witnesses.')
    add('Primary key fingerprint: ' + data['primary_fingerprint'], 'small')
    add(f"The earliest {MAX_EVENTS} linked events at most are included. {data['omitted']} events are omitted and not checked by this export. "
        'If evidence is unsealed, unavailable, or verification was skipped, it is NOT CHECKED. '
        'Any observed failed check makes the report FAILED. Incomplete coverage cannot receive an overall VERIFIED status.')
    add('Event and raw record IDs below can be opened in the signed-in ANVAYA workspace. Raw payloads and AI responses '
        'are not embedded. This PDF contains device names, addresses and analyst notes; share it only with intended recipients. '
        'Unsupported characters are represented by their Unicode code points (for example [U+1F512]).')
    add('Detection timeline', 'h')
    for stage in d['stages_detail']:
        add(f"{stage['label']} | {stamp(stage['first_time'])} | {stage['event_count']} events", 'label')
        add(stage['headline'])
    add('Investigation notes and history', 'h')
    add(f"Latest {len(data['activity'])} of {data['activity_total']} activity entries; "
        f"{data['activity_total'] - len(data['activity'])} older entries omitted.", 'small')
    if not data['activity']:
        add('No investigation activity recorded.')
    for entry in reversed(data['activity']):
        add(f"{stamp(entry['at'])} | {entry['actor']} | {entry['state']} | "
            f"controlled test: {'yes' if entry['controlled_test'] else 'no'}", 'label')
        add(entry['note'] or 'Status/label updated; no note added.')
    story.append(PageBreak())
    add('Linked evidence', 'title')
    if not data['events']:
        add('No linked normalized events are available. Integrity is NOT CHECKED.')
    for index, event in enumerate(data['events'], 1):
        block_start = len(story)
        check = data['checks'][event['raw_id']]
        add(f"{index:03d} / {event['event_id']} / {check['status']}", 'h')
        add(f"{stamp(event['time'])} | {event['device']} | {event['class_name']} | "
            f"{event.get('action') or event.get('status') or 'Observed'}")
        add(event.get('title') or event.get('activity_name') or 'Untitled event')
        add(f"Source: {event.get('src_ip') or '-'}:{event.get('src_port') or '-'}  |  "
            f"Destination: {event.get('dst_ip') or '-'}:{event.get('dst_port') or '-'}  |  "
            f"User: {event.get('user_name') or '-'}", 'small')
        add(f"Raw: {event['raw_id']} | Batch: {event.get('batch_id') or 'Not sealed'} | {check['reason']}", 'small')
        if 'stored_hash' in check:
            add(f"Stored SHA-256: {check['stored_hash']}\nCurrent SHA-256: {check['current_hash']}", 'small')
            add(f"Configured witness heads checked: {check['witness_count']}", 'small')
        story.append(Spacer(1, 5))
        block = story[block_start:]
        del story[block_start:]
        story.append(KeepTogether(block))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d8dfe3'))
        canvas.line(42, 36, A4[0] - 42, 36)
        canvas.setFont('Report', 7)
        canvas.setFillColor(muted)
        canvas.drawString(42, 24, 'ANVAYA / Private incident snapshot / All times UTC')
        canvas.drawRightString(A4[0] - 42, 24, f'Page {doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()

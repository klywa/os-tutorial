"""Build a ZIP of the formal reading documents for a single season."""
from io import BytesIO
import re
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

import json_store
from lineup_layout import reading_document
import seasons
from website_data import sanitize


def note_markdown(title, reading):
    if 'markdown' in reading:
        return reading['markdown']
    opening = reading.get('opening')
    sections = ('## ' + part['title'] + '\n\n' + part['markdown']
                for part in reading['sections'])
    return '# ' + title + '\n\n' + (opening + '\n\n' if opening else '') + '\n'.join(sections)


def filename_stem(value):
    value = unicodedata.normalize('NFC', value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value).strip(' .')
    value = value.encode('utf-8')[:120].decode('utf-8', 'ignore').rstrip(' .') or '笔记'
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]', value.split('.')[0], re.I):
        value = '_' + value
    return value


def build_archive(root, season):
    records = seasons.members(root, season)
    if not records:
        raise ValueError('当前赛季没有可导出的笔记')
    output = BytesIO()
    used = set()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for note_id in sorted(records):
            note = json_store.resolve_note(root, note_id)
            if not note or not seasons.matches(note, season) or note['revision'] != records[note_id]['revision']:
                raise ValueError('笔记版本已更新，请重新导出')
            title = note['title']
            reading = reading_document(note)
            players = reading.get('player_options')
            versions = [(title, reading)] if not players else [
                (title + ' - ' + player['name'], reading_document(note, player['id']))
                for player in players
            ]
            for label, document in versions:
                stem = filename_stem(label)
                name = stem + '.md'
                if name.casefold() in used:
                    stem += ' - ' + filename_stem(note_id)
                    name = stem + '.md'
                serial = 2
                while name.casefold() in used:
                    name = f'{stem} - {serial}.md'
                    serial += 1
                used.add(name.casefold())
                archive.writestr(name, note_markdown(title, sanitize(document)).encode('utf-8'))
    if seasons.members(root, season) != records:
        raise ValueError('笔记版本已更新，请重新导出')
    return output.getvalue()


def send_archive(handler, root, season):
    body = build_archive(root, season)
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/zip')
    handler.send_header('Content-Disposition', f'attachment; filename="wanxiangqi-notes-{season}.zip"')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    handler.wfile.write(body)

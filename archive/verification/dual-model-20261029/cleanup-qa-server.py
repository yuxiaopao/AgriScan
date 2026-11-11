"""Exact tagged QA cleanup. No network or database is touched when imported."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import MetaData, and_, create_engine, delete, insert, select, text

ROOT = Path('/srv/agriscan')
ID = re.compile(r'[a-f0-9]{32}')
SHA = re.compile(r'[a-f0-9]{64}')
IMAGE = re.compile(r'[a-f0-9]{32}\.jpg')
QA_TABLES = ('detections', 'detection_predictions', 'plots', 'plot_details',
             'assistant_detection_discussions', 'assistant_conversations', 'assistant_messages')


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def encoded(value):
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, bytes): return {'base64': base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=encoded).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_plan(plan):
    require(set(plan) == {'run_tag', 'expected_current', 'owner_id', 'detections', 'plots',
                          'expected_configuration_version', 'expected_configuration_sha256'}, 'plan_fields')
    require(type(plan['expected_configuration_version']) is int and plan['expected_configuration_version'] >= 0,
            'expected_configuration_version')
    require(isinstance(plan['expected_configuration_sha256'], str)
            and bool(SHA.fullmatch(plan['expected_configuration_sha256'])), 'expected_configuration_sha256')
    require(isinstance(plan['run_tag'], str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{11,100}', plan['run_tag']), 'run_tag')
    require(bool(ID.fullmatch(plan['owner_id'])), 'owner_id')
    require(isinstance(plan['expected_current'], str) and re.fullmatch(
        r'/srv/agriscan/releases/release-[a-z0-9-]{6,100}', plan['expected_current']), 'expected_release')
    require(isinstance(plan['detections'], list) and isinstance(plan['plots'], list), 'scope_lists')
    require(0 < len(plan['detections']) + len(plan['plots']) <= 64, 'scope_size')
    seen = set()
    for item in plan['detections']:
        require(set(item) == {'id', 'name', 'note', 'image_url', 'source_image_sha256', 'conversation_id'}, 'detection_fields')
        require(bool(ID.fullmatch(item['id'])) and item['id'] not in seen, 'detection_id')
        seen.add(item['id'])
        require(isinstance(item['name'], str) and 0 < len(item['name']) <= 200, 'detection_name')
        require(isinstance(item['note'], str) and plan['run_tag'] in item['note'], 'detection_note_tag')
        require(isinstance(item['image_url'], str) and item['image_url'].startswith('/api/uploads/')
                and bool(IMAGE.fullmatch(item['image_url'].removeprefix('/api/uploads/'))), 'detection_image_url')
        require(bool(SHA.fullmatch(item['source_image_sha256'])), 'detection_source_image_sha')
        require(item['conversation_id'] is None or bool(ID.fullmatch(item['conversation_id'])), 'conversation_id')
    seen = set()
    for item in plan['plots']:
        require(set(item) == {'id', 'name', 'crop', 'area', 'location', 'manager', 'cover_filename', 'cover_sha256'}, 'plot_fields')
        require(bool(ID.fullmatch(item['id'])) and item['id'] not in seen, 'plot_id')
        seen.add(item['id'])
        require(plan['run_tag'] in item['name'] or plan['run_tag'] in item['location'], 'plot_tag')
        require((item['cover_filename'] is None and item['cover_sha256'] is None)
                or (isinstance(item['cover_filename'], str) and bool(IMAGE.fullmatch(item['cover_filename']))
                    and isinstance(item['cover_sha256'], str) and bool(SHA.fullmatch(item['cover_sha256']))), 'plot_cover')
    conversations = [row['conversation_id'] for row in plan['detections'] if row['conversation_id']]
    require(len(conversations) == len(set(conversations)), 'conversations_must_be_exclusive')
    return plan


def selected(connection, table, condition=None, lock=False):
    query = select(table)
    if condition is not None: query = query.where(condition)
    if lock: query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def one(items, code):
    require(len(items) == 1, code)
    return items[0]


def collect(connection, tables, plan, lock=False):
    qa = {name: [] for name in QA_TABLES}
    D, P, PD = (tables[name] for name in ('detections', 'plots', 'plot_details'))
    DD, C, M = (tables[name] for name in ('assistant_detection_discussions', 'assistant_conversations', 'assistant_messages'))
    detection_ids = {row['id'] for row in plan['detections']}
    files = {}
    for expected in plan['plots']:
        row = one(selected(connection, P, P.c.id == expected['id'], lock), 'exact_qa_plot_missing')
        require(row['owner_id'] == plan['owner_id'], 'plot_owner_changed')
        require(all(row[key] == expected[key] for key in ('name', 'crop', 'location', 'manager'))
                and Decimal(str(row['area'])) == Decimal(str(expected['area'])), 'plot_markers_changed')
        linked = selected(connection, D, D.c.plot_id == row['id'], lock)
        require(all(item['id'] in detection_ids and item['owner_id'] == plan['owner_id'] for item in linked), 'plot_has_non_qa_detections')
        details = selected(connection, PD, PD.c.plot_id == row['id'], lock)
        require(len(details) <= 1 and (details[0]['cover_filename'] if details else None) == expected['cover_filename'], 'plot_cover_changed')
        qa['plots'].append(row); qa['plot_details'].extend(details)
        if expected['cover_filename']:
            files[expected['cover_filename']] = expected['cover_sha256']
    for expected in plan['detections']:
        row = one(selected(connection, D, D.c.id == expected['id'], lock), 'exact_qa_detection_missing')
        require(row['owner_id'] == plan['owner_id'] and not row['is_demo'], 'detection_owner_changed')
        require(all(row[key] == expected[key] for key in ('name', 'note', 'image_url')), 'detection_markers_changed')
        qa['detections'].append(row)
        qa['detection_predictions'].extend(selected(connection, tables['detection_predictions'],
                                                    tables['detection_predictions'].c.detection_id == row['id'], lock))
        filename = expected['image_url'].removeprefix('/api/uploads/')
        require(filename not in files or files[filename] == expected['source_image_sha256'], 'shared_qa_photo_sha_conflict')
        files[filename] = expected['source_image_sha256']
        links = selected(connection, DD, DD.c.detection_id == row['id'], lock)
        if expected['conversation_id'] is None:
            require(not links, 'unlisted_qa_conversation')
            continue
        link = one(links, 'discussion_not_exclusive')
        require(link['user_id'] == plan['owner_id'] and link['conversation_id'] == expected['conversation_id'], 'discussion_owner_changed')
        chat = one(selected(connection, C, C.c.id == expected['conversation_id'], lock), 'exact_qa_conversation_missing')
        require(chat['user_id'] == plan['owner_id'] and chat['title'] != '你好', 'conversation_owner_or_protected_title')
        require(chat['busy_until'] is None or chat['busy_until'].replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None), 'qa_conversation_busy')
        require(selected(connection, DD, DD.c.conversation_id == chat['id'], lock) == links, 'conversation_used_by_another_detection')
        messages = selected(connection, M, M.c.conversation_id == chat['id'], lock)
        require(any(message['role'] == 'user' and plan['run_tag'] in message['content'] and expected['name'] in message['content'] for message in messages), 'conversation_lacks_qa_source_markers')
        qa['assistant_detection_discussions'].append(link)
        qa['assistant_conversations'].append(chat)
        qa['assistant_messages'].extend(messages)
    scopes = qa_conditions(tables, qa)
    for filename in files:
        require(not selected(connection, D, and_(D.c.image_url == '/api/uploads/' + filename,
                    ~D.c.id.in_(detection_ids))), 'qa_photo_used_by_non_qa_detection')
        require(not selected(connection, PD, and_(PD.c.cover_filename == filename,
                    ~PD.c.plot_id.in_([item['id'] for item in qa['plots']]))), 'qa_photo_used_by_non_qa_cover')
    # Refuse future schema relationships rather than cascade into unknown data.
    for table in tables.values():
        for constraint in table.foreign_key_constraints:
            elements = list(constraint.elements)
            if not elements or elements[0].column.table.name not in {'detections', 'plots', 'assistant_conversations'}: continue
            require(len(elements) == 1 and elements[0].column.name == 'id', 'unexpected_composite_foreign_key')
            target = elements[0].column.table.name
            ids = [item['id'] for item in qa[target]]
            if not ids: continue
            linked = selected(connection, table, elements[0].parent.in_(ids), lock)
            allowed = {digest(row) for row in qa.get(table.name, [])}
            require(all(digest(row) in allowed for row in linked), 'non_qa_foreign_reference')
    return qa, files, scopes


def qa_conditions(tables, qa):
    conditions = {}
    for name, values in qa.items():
        table = tables[name]
        if name == 'assistant_detection_discussions':
            conditions[name] = and_(table.c.user_id.in_([row['user_id'] for row in values]),
                                    table.c.detection_id.in_([row['detection_id'] for row in values]),
                                    table.c.conversation_id.in_([row['conversation_id'] for row in values]))
        else:
            key = next(iter(table.primary_key.columns))
            conditions[name] = key.in_([row[key.name] for row in values])
    return conditions


def fingerprints(connection, tables, scopes, omit_audits=()):
    state = {}
    for name, table in tables.items():
        query = select(table)
        if name in scopes: query = query.where(~scopes[name])
        if name == 'audit_logs' and omit_audits: query = query.where(~table.c.id.in_(omit_audits))
        result = {}
        for row in connection.execute(query).mappings():
            value = dict(row)
            key = [value[column.name] for column in table.primary_key.columns]
            result[digest(key if key else value)] = digest(value)
        state[name] = result
    return state


def summary(state):
    return {name: {'rows': len(rows), 'sha256': digest(rows)} for name, rows in sorted(state.items())}


def runtime_state(connection, tables):
    revision = one(selected(connection, tables['alembic_version']), 'schema_revision_rows')['version_num']
    config = one(selected(connection, tables['workspace_configuration']), 'configuration_rows')
    require(revision == '20261029_06', 'schema_revision_changed')
    checksum = digest(config)  # Synthetic SQLite helper tests only.
    if connection.dialect.name == 'mysql':
        # Exactly the same public row checksum used by activation/runtime probes.
        checksum = connection.execute(text("SELECT SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),"
            "COALESCE(encrypted_secrets,''),COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) "
            "FROM workspace_configuration WHERE id='workspace'")).scalar_one()
    require(isinstance(checksum, str) and bool(SHA.fullmatch(checksum)), 'configuration_checksum_shape')
    return {'schema': revision, 'configuration_version': config['version'], 'configuration_sha256': checksum}


def check_runtime_plan(state, plan):
    require(state['configuration_version'] == plan['expected_configuration_version']
            and state['configuration_sha256'] == plan['expected_configuration_sha256'], 'configuration_baseline_changed')


def checked_file(folder, name, expected_sha):
    require(bool(IMAGE.fullmatch(name)), 'image_filename')
    path = folder / name
    require(path.parent.resolve() == folder and path.is_file() and not path.is_symlink(), 'qa_photo_unavailable')
    require(file_sha(path) == expected_sha, 'qa_photo_sha_changed')
    return path


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data); output.flush(); os.fsync(output.fileno())
    require(stat.S_IMODE(path.stat().st_mode) == 0o600, 'backup_file_permissions')


def delete_exact(connection, tables, qa, scopes, owner):
    audits = []
    # Delete the exclusive child messages/discussion first; no other chat is touched.
    for name in ('assistant_detection_discussions', 'assistant_messages', 'assistant_conversations',
                 'detection_predictions', 'detections', 'plot_details', 'plots'):
        if not qa[name]: continue
        result = connection.execute(delete(tables[name]).where(scopes[name]))
        require(result.rowcount == len(qa[name]), 'exact_delete_rowcount_changed')
        if name in {'detections', 'plots'}:
            for row in qa[name]:
                audit_id = uuid4().hex; audits.append(audit_id)
                connection.execute(insert(tables['audit_logs']).values(id=audit_id, actor_id=owner['id'],
                    actor_name=owner['username'][:80], action='delete',
                    resource_type='detection' if name == 'detections' else 'plot', resource_id=row['id'],
                    summary=('删除检测样本：' if name == 'detections' else '删除地块并保留历史检测：') + row['name'],
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    return audits


def read_private_runtime():
    fields = {}
    pattern = re.compile(r'^\s*(?:export\s+)?(DATABASE_URL|UPLOAD_DIR|REDIS_URL)\s*=')
    with (ROOT / 'shared/production.env').open(encoding='utf-8') as stream:
        for line in stream:
            if pattern.match(line):
                fields.update(dotenv_values(stream=io.StringIO(line), interpolate=False))
    require(fields.get('DATABASE_URL') and fields.get('UPLOAD_DIR'), 'private_runtime_fields_unavailable')
    require(fields['DATABASE_URL'].startswith('mysql+pymysql://'), 'production_database_required')
    return fields


def execute(plan, apply=False):
    validate_plan(plan)
    require(str((ROOT / 'current').resolve()) == plan['expected_current'], 'current_release_changed')
    env = read_private_runtime()
    folder = Path(env['UPLOAD_DIR']).resolve()
    require(folder.is_dir(), 'upload_directory_unavailable')
    engine = create_engine(env['DATABASE_URL'], pool_pre_ping=True, echo=False, isolation_level='REPEATABLE READ')
    report = {'status': 'prepared_read_only', 'mode': 'apply' if apply else 'inspect',
              'run_tag': plan['run_tag'], 'plan_sha256': digest(plan), 'mutations': []}
    backup = None
    try:
        metadata = MetaData(); metadata.reflect(bind=engine); tables = metadata.tables
        require(set(QA_TABLES) | {'users', 'audit_logs', 'alembic_version', 'workspace_configuration'} <= set(tables), 'expected_tables_unavailable')
        with engine.begin() as connection:
            users = tables['users']
            owner = one(selected(connection, users, users.c.id == plan['owner_id']), 'exact_qa_owner_missing')
            require(owner['role'] == 'admin' and owner['is_active'], 'qa_owner_not_active_admin')
            qa, files, scopes = collect(connection, tables, plan, lock=apply)
            state = runtime_state(connection, tables)
            check_runtime_plan(state, plan)
            before = fingerprints(connection, tables, scopes)
            for name, sha in files.items(): checked_file(folder, name, sha)
            report.update({'qa_row_counts': {name: len(rows) for name, rows in qa.items()},
                           'qa_rows_sha256': digest(qa), 'qa_photo_sha256': files,
                           'runtime_before': state, 'non_qa_before': summary(before)})
            if apply:
                backup_base = (ROOT / 'shared/backups').resolve()
                backup = backup_base / ('qa-' + plan['run_tag'].replace(':', '-') + '-' + uuid4().hex[:8])
                require(backup.parent == backup_base and not backup.is_symlink(), 'backup_path')
                backup.mkdir(mode=0o700)
                os.chmod(backup, 0o700)
                private_write(backup / 'qa-rows.json', canonical({'plan': plan, 'rows': qa, 'runtime': state}))
                for name, sha in files.items():
                    source = checked_file(folder, name, sha)
                    private_write(backup / name, source.read_bytes())
                require(digest(collect(connection, tables, plan, lock=True)[0]) == digest(qa), 'qa_rows_changed_during_backup')
                audit_ids = delete_exact(connection, tables, qa, scopes, owner)
                after = fingerprints(connection, tables, scopes, audit_ids)
                require(after == before, 'non_qa_snapshot_changed_by_cleanup')
                require(runtime_state(connection, tables) == state, 'configuration_changed_by_cleanup')
                report.update({'non_qa_after_transaction': summary(after), 'non_qa_snapshot_unchanged': True,
                               'appended_normal_delete_audits': audit_ids, 'backup': str(backup)})
        if apply:
            report['mutations'].append('one transaction: exact tagged QA rows only; append normal delete audit rows')
            # Only after commit, remove validated unshared QA photographs.
            removed = []
            with engine.connect() as connection:
                D, PD = tables['detections'], tables['plot_details']
                for name, sha in files.items():
                    require(not selected(connection, D, D.c.image_url == '/api/uploads/' + name)
                            and not selected(connection, PD, PD.c.cover_filename == name), 'photo_reference_appeared_after_commit')
                    checked_file(folder, name, sha).unlink()
                    removed.append(name)
                observed = fingerprints(connection, tables, scopes, audit_ids)
                require(runtime_state(connection, tables) == state, 'configuration_changed_concurrently')
            report['removed_qa_photos'] = removed
            report['non_qa_after_observed'] = summary(observed)
            report['concurrent_non_qa_changes'] = {name: {'added': len(set(observed[name]) - set(before[name])),
                'removed': len(set(before[name]) - set(observed[name])),
                'updated': sum(observed[name][key] != value for key, value in before[name].items() if key in observed[name])}
                for name in before if observed[name] != before[name]}
            try:
                sys.path.insert(0, str(ROOT / 'current/backend'))
                from app.cache import DashboardCache
                cache = DashboardCache(env.get('REDIS_URL') or '')
                try: cache.invalidate(plan['owner_id'])
                finally: cache.close()
                report['owner_cache_invalidated'] = True
            except Exception:
                report['owner_cache_invalidated'] = False
                report['cache_warning'] = 'QA deletion committed; normal cache TTL bounds any stale statistics.'
            report['status'] = 'passed'
            private_write(backup / 'cleanup-report.json', canonical(report))
        return report
    except Exception as error:
        return {**report, 'status': 'refused_or_incomplete', 'error': str(error) if isinstance(error, Refused) else type(error).__name__,
                'backup': str(backup) if backup else None}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-base64', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        plan = json.loads(base64.b64decode(args.plan_base64, validate=True))
        report = execute(plan, apply=args.apply)
    except Exception as error:
        report = {'status': 'refused_or_incomplete', 'error': str(error) if isinstance(error, Refused) else type(error).__name__}
    print('RESULT ' + json.dumps(report, ensure_ascii=False), flush=True)
    raise SystemExit(0 if report['status'] in {'passed', 'prepared_read_only'} else 1)


if __name__ == '__main__':
    main()

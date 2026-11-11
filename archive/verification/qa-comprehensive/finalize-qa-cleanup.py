"""Reviewed cleanup wrapper with pre/post production integrity fingerprints."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import httpx

RUN = 'qa20261028_1935'
CORE_SHA = '0fdccd3ae777fc174e0c195ed76838cf11959dce87ec28f90ba0ad36b5541797'
MODEL_SHA = 'ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773'
ORIGINAL_ARTICLES = {'corn-leaf', 'cucumber-humidity', 'rice-scouting', 'tomato-early-blight'}
REPORT = Path('/srv/agriscan/shared/logs/qa20261028_1935-final-cleanup-integrity.json')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def integrity(core):
    from sqlalchemy import create_engine, event, func, select
    from sqlalchemy.orm import Session
    from app.db import AppMeta, User, Detection, Plot
    from app.admin_models import KnowledgeArticle, AuditLog
    from app.runtime_config import WorkspaceConfiguration
    engine = create_engine(core.read_environment()['DATABASE_URL'], echo=False, hide_parameters=True)

    @event.listens_for(engine, 'before_cursor_execute')
    def readonly(_conn, _cursor, statement, _params, _context, _many):
        require(statement.lstrip().split(None, 1)[0].upper() in {'SELECT', 'SHOW'}, 'INTEGRITY_NON_READ_SQL')

    try:
        with Session(engine, autoflush=False) as db:
            managed = db.scalar(select(AppMeta.value).where(AppMeta.key == 'managed_admin_id'))
            original_admin = db.execute(select(User.__table__).where(User.id == managed)).mappings().one()
            require(original_admin['role'] == 'admin' and original_admin['is_active'], 'ORIGINAL_ADMIN_NOT_ACTIVE')
            original_articles = [dict(row) for row in db.execute(select(KnowledgeArticle.__table__)
                .where(KnowledgeArticle.id.in_(ORIGINAL_ARTICLES)).order_by(KnowledgeArticle.id)).mappings()]
            require(len(original_articles) == 4, 'ORIGINAL_KNOWLEDGE_COUNT_CHANGED')
            configuration = [dict(row) for row in db.execute(select(WorkspaceConfiguration.__table__)
                .order_by(WorkspaceConfiguration.id)).mappings()]
            audits = sorted(db.scalars(select(AuditLog.id)).all())
            count = lambda model: db.scalar(select(func.count()).select_from(model))
            data = {'original_admin_id': managed, 'original_admin_sha256': fingerprint(dict(original_admin)),
                    'original_knowledge_ids': [row['id'] for row in original_articles],
                    'original_knowledge_sha256': fingerprint(original_articles),
                    'configuration_database_sha256': fingerprint(configuration),
                    'audit_ids_sha256': fingerprint(audits), 'audit_rows': len(audits),
                    'users': count(User), 'qa_users': db.scalar(select(func.count()).select_from(User).where(User.id.in_(core.USER_IDS))),
                    'detections': count(Detection), 'plots': count(Plot)}
            db.rollback()
    finally:
        engine.dispose()
    folder = Path('/srv/agriscan/current/model')
    with (folder / 'model.onnx').open('rb') as source:
        data['model_onnx_sha256'] = hashlib.file_digest(source, 'sha256').hexdigest()
    require(data['model_onnx_sha256'] == MODEL_SHA, 'MODEL_HASH_CHANGED')
    data['model_manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
    with httpx.Client(trust_env=False, timeout=20) as client:
        response = client.get('https://flowly-ai.top/agriscan/api/health')
        require(response.status_code == 200, 'PUBLIC_HEALTH_HTTP_ERROR')
        data['health'] = response.json()
        require(data['health'] == {'status': 'ok', 'database': 'connected', 'redis': 'connected',
                                   'mode': 'production', 'model': 'ready'}, 'HEALTH_DEGRADED')
        response = client.get('https://flowly-ai.top/agriscan/api/client/config')
        require(response.status_code == 200, 'PUBLIC_CONFIGURATION_HTTP_ERROR')
        public = response.json()
        require(public['version'] == 5, 'CONFIGURATION_VERSION_NOT_FIVE')
        data['configuration_public_version'] = public['version']
        data['configuration_public_sha256'] = fingerprint(public)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-run')
    args = parser.parse_args()
    require((args.apply and args.confirm_run == RUN) or (not args.apply and args.confirm_run is None),
            'EXPLICIT_APPLY_CONFIRMATION_REQUIRED')
    source = Path(__file__).with_name('cleanup-qa-accounts.py')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == CORE_SHA, 'REVIEWED_CORE_SHA_MISMATCH')
    spec = importlib.util.spec_from_file_location('reviewed_qa_cleanup', source)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    report = {'run_id': RUN, 'started_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'apply' if args.apply else 'preview', 'core_sha256': CORE_SHA, 'committed': False}
    try:
        preview = core.execute_cleanup(False)
        report['preview'] = preview
        require(preview['planned_delete_counts'] == {
            'assistant_detection_discussions': 0, 'assistant_messages': 0, 'assistant_conversations': 1,
            'user_emails': 0, 'knowledge_articles': 1, 'users': 3}, 'REVIEWED_IMPACT_COUNTS_CHANGED')
        report['before'] = integrity(core)
        if args.apply:
            report['cleanup'] = core.execute_cleanup(True)
            report['committed'] = True
            report['after'] = integrity(core)
            keys = ('original_admin_id', 'original_admin_sha256', 'original_knowledge_ids',
                    'original_knowledge_sha256', 'configuration_database_sha256',
                    'model_onnx_sha256', 'model_manifest_sha256',
                    'configuration_public_version', 'configuration_public_sha256', 'health')
            require(all(report['before'][key] == report['after'][key] for key in keys), 'POST_CLEANUP_INTEGRITY_MISMATCH')
            require(report['after']['qa_users'] == 0
                    and report['after']['users'] >= report['before']['users'] - 3 >= 1,
                    'UNEXPECTED_FINAL_USER_COUNT')
            require(report['after']['audit_rows'] >= report['before']['audit_rows'], 'AUDIT_ROWS_MISSING')
            report['business_preservation'] = {
                'scope': 'No Detection/Plot or non-QA User DELETE is allowed by the reviewed core.',
                'concurrent_non_qa_additions_allowed': True,
                'detections_before': report['before']['detections'], 'detections_after': report['after']['detections'],
                'plots_before': report['before']['plots'], 'plots_after': report['after']['plots']}
            report['status'] = 'passed_applied_and_verified'
        else:
            report['status'] = 'preview_only_no_database_writes'
    except Exception as error:
        report['status'] = 'failed_check_after_commit' if report['committed'] else 'aborted_before_verified_commit'
        report['error_type'] = type(error).__name__
        report['safe_reason'] = str(error) if isinstance(error, core.SafetyAbort) else 'DETAILS_REDACTED'
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': report['status'], 'report': str(REPORT), 'error_type': type(error).__name__}))
        return 1
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    REPORT.chmod(0o600)
    print(json.dumps({'status': report['status'], 'report': str(REPORT),
                      'planned_delete_counts': preview['planned_delete_counts'],
                      'before': report['before'], 'after': report.get('after')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

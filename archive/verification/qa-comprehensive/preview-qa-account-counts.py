"""One-shot SELECT-only impact count; this program has no mutation mode."""
import json
from pathlib import Path
import sys

sys.path.insert(0, '/srv/agriscan/current/backend')
from sqlalchemy import create_engine, event, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db import User, AppMeta
from app.assistant import Conversation, ChatMessage
from app.detection_assistant import DetectionDiscussion
from app.extensions import UserEmail
from app.admin_models import KnowledgeArticle, AuditLog
from app.runtime_config import WorkspaceConfiguration

RUN = 'qa20261028_1935'
EXPECTED = {'qa20261028_1935_member': '24aa4abfcbfd43eabc523737f2ca4e0f',
            'qa20261028_1935_disabled': '708236d223694fedbb18c1917ed381ee',
            'qa20261028_1935_registered': 'b120f98472994ee2971c8b2ec3a05c18'}
ARTICLE = '73f83d9c50e7488cb8e79c4d22a412ee'


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    values = {}
    for line in Path('/srv/agriscan/shared/production.env').read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key in {'DATABASE_URL', 'DEMO_MODE'}:
            values[key] = value.strip().strip('\"\'')
    url = make_url(values['DATABASE_URL'])
    check(url.drivername == 'mysql+pymysql' and url.host == '127.0.0.1' and url.port == 3306
          and url.username == 'agriscan' and url.database == 'agriscan'
          and values.get('DEMO_MODE') == 'false', 'Production database identity mismatch.')
    engine = create_engine(url, echo=False)

    @event.listens_for(engine, 'before_cursor_execute')
    def readonly(_connection, _cursor, statement, _parameters, _context, _many):
        check(statement.lstrip().split(None, 1)[0].upper() in {'SELECT', 'SHOW', 'DESCRIBE'},
              'Read-only preview blocked a non-read statement.')

    ids = list(EXPECTED.values())
    with Session(engine, autoflush=False) as db:
        users = db.scalars(select(User).where(or_(User.id.in_(ids), User.username.in_(list(EXPECTED))))).all()
        check({row.username: row.id for row in users} == EXPECTED and len(users) == 3, 'User allowlist mismatch.')
        check(all(row.role == 'member' for row in users), 'QA user role changed.')
        marker = db.get(AppMeta, 'managed_admin_id')
        check(marker is not None and marker.value not in ids, 'Managed administrator protection failed.')
        admin = db.get(User, marker.value)
        check(admin is not None and admin.role == 'admin' and admin.is_active, 'Managed administrator is unavailable.')
        article = db.get(KnowledgeArticle, ARTICLE)
        check(article is not None and article.status == 'archived' and article.title.startswith(RUN),
              'Article id, status, or title prefix mismatch.')
        def count(model, *conditions):
            return db.scalar(select(func.count()).select_from(model).where(*conditions))
        conv = db.scalars(select(Conversation).where(Conversation.user_id.in_(ids))).all()
        owners = {row.id: row.user_id for row in conv}
        links = db.scalars(select(DetectionDiscussion).where(or_(DetectionDiscussion.user_id.in_(ids),
                           DetectionDiscussion.conversation_id.in_(list(owners))))).all()
        check(all(row.user_id in ids and owners.get(row.conversation_id) == row.user_id for row in links),
              'A selected discussion crosses the QA user boundary.')
        other_articles = count(KnowledgeArticle, KnowledgeArticle.id != ARTICLE,
                               or_(KnowledgeArticle.created_by.in_(ids), KnowledgeArticle.updated_by.in_(ids)))
        check(other_articles == 0, 'QA users reference an unapproved article.')
        check(count(WorkspaceConfiguration, WorkspaceConfiguration.updated_by.in_(ids)) == 0,
              'A QA user is referenced by runtime configuration.')
        data = {'run_id': RUN, 'mode': 'readonly_preview', 'users': EXPECTED, 'article_id': ARTICLE,
                'checks': {'production_database': True, 'managed_admin_protected': True,
                           'article_archived_and_prefixed': True, 'no_cross_user_discussions': True,
                           'no_other_articles_or_config_references': True},
                'planned_delete_counts': {'users': 3, 'knowledge_articles': 1,
                    'assistant_detection_discussions': len(links),
                    'assistant_messages': count(ChatMessage, ChatMessage.conversation_id.in_(list(owners))),
                    'assistant_conversations': len(conv), 'user_emails': count(UserEmail, UserEmail.user_id.in_(ids))},
                'preserve': {'audit_total': count(AuditLog),
                             'audit_actor_ids_automatically_set_null': count(AuditLog, AuditLog.actor_id.in_(ids)),
                             'non_qa_users': count(User, User.id.not_in(ids)),
                             'non_qa_conversations': count(Conversation, Conversation.user_id.not_in(ids))},
                'database_mutations_sent': 0}
        db.rollback()
    engine.dispose()
    Path('/srv/agriscan/shared/logs/qa20261028_1935-account-cleanup-preview-counts.json').write_text(
        json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'preview_refused', 'error_type': type(error).__name__}))
        raise SystemExit(1)

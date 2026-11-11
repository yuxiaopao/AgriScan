"""Prepare exact QA-account cleanup. Default: SELECT/SHOW preview only.

Server use only after review. --apply --confirm-run qa20261028_1935 is required
for a single atomic cleanup transaction. No app.main, migrations or model startup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

RUN = "qa20261028_1935"
# Copied from the run_id-checked, private fixtures; no fixture passwords/emails.
USERS = {
    "qa20261028_1935_member": "24aa4abfcbfd43eabc523737f2ca4e0f",
    "qa20261028_1935_disabled": "708236d223694fedbb18c1917ed381ee",
    "qa20261028_1935_registered": "b120f98472994ee2971c8b2ec3a05c18",
}
USER_IDS = tuple(USERS.values())
ARTICLE_ID = "73f83d9c50e7488cb8e79c4d22a412ee"
BACKEND = Path("/srv/agriscan/current/backend")
ENV_FILE = Path("/srv/agriscan/shared/production.env")
LOG_DIR = Path("/srv/agriscan/shared/logs")
DELETE_TABLES = {
    "assistant_detection_discussions", "assistant_messages",
    "assistant_conversations", "user_emails", "knowledge_articles", "users",
}


class SafetyAbort(Exception):
    """Fixed reason codes only; never print database errors or bound values."""


def require(condition, code):
    if not condition:
        raise SafetyAbort(code)


def read_environment():
    wanted = {"DATABASE_URL", "DEMO_MODE", "ADMIN_USERNAME"}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, raw = stripped.partition("=")
        key = key.strip()
        if not separator or key not in wanted:
            continue
        require(key not in result, "DUPLICATE_REQUIRED_ENV_KEY")
        raw = raw.strip()
        if raw.startswith(("'", '"')):
            match = re.fullmatch(r"(['\"])(.*?)\1\s*(?:#.*)?", raw)
            require(match is not None, "UNSUPPORTED_ENV_QUOTING")
            value = match.group(2)
        else:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
        require(bool(value), "EMPTY_REQUIRED_ENV_VALUE")
        result[key] = value
    require(set(result) == wanted, "MISSING_REQUIRED_ENV_KEY")
    require(result["DEMO_MODE"].lower() == "false", "DEMO_MODE_NOT_FALSE")
    return result


def write_report(report):
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = LOG_DIR / f"{RUN}-accounts-{report['mode']}-{stamp}-{os.getpid()}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # Report has identifiers/counts only. Do not add exception text or env values.
    print(json.dumps({"report": str(path), **report}, ensure_ascii=False))


def emit_report(report):
    try:
        write_report(report)
        return True
    except Exception as error:
        # Suppress traceback chains even if logging fails while handling a DB error.
        try:
            print(json.dumps({"run_id": RUN, "mode": report["mode"],
                              "status": report["status"],
                              "error_type": type(error).__name__,
                              "reason_code": "REPORT_WRITE_FAILED"}))
        except Exception:
            pass
        return False


def execute_cleanup(apply):
    from sqlalchemy import create_engine, delete, event, func, or_, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Delete

    env = read_environment()
    url = make_url(env["DATABASE_URL"])
    require((url.drivername, url.username, url.host, url.port, url.database)
            == ("mysql+pymysql", "agriscan", "127.0.0.1", 3306, "agriscan"),
            "UNEXPECTED_DATABASE_TARGET")
    require(bool(url.password), "DATABASE_PASSWORD_MISSING")
    require(set(url.query) <= {"charset"}
            and url.query.get("charset", "utf8mb4") == "utf8mb4",
            "UNEXPECTED_DATABASE_URL_OPTIONS")
    require(BACKEND.is_dir(), "SERVER_BACKEND_NOT_FOUND")
    sys.path.insert(0, str(BACKEND))
    from app.db import AppMeta, Detection, DetectionPrediction, Plot, PlotDetails, RevokedToken, User
    from app.assistant import ChatMessage, Conversation
    from app.detection_assistant import DetectionDiscussion
    from app.extensions import EmailChallenge, ModelArtifact, UserEmail
    from app.admin_models import AuditLog, KnowledgeArticle
    from app.runtime_config import WorkspaceConfiguration
    require("app.main" not in sys.modules, "APP_MAIN_IMPORTED")

    engine = create_engine(url, echo=False, hide_parameters=True,
                           connect_args={"connect_timeout": 10, "read_timeout": 20,
                                         "write_timeout": 20, "autocommit": False})

    @event.listens_for(engine, "before_cursor_execute")
    def sql_guard(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.lstrip()
        verb = normalized.split(None, 1)[0].upper() if normalized else ""
        if verb in {"SELECT", "SHOW"}:
            require(not re.search(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", normalized, re.I),
                    "FILE_OUTPUT_SQL_REJECTED")
            if not apply:
                require(not re.search(r"\bFOR\s+UPDATE\b|\bLOCK\s+IN\s+SHARE\b", normalized, re.I),
                        "PREVIEW_LOCK_REJECTED")
            return
        compiled = getattr(context, "compiled", None)
        compiled_statement = getattr(compiled, "statement", None)
        require(apply and verb == "DELETE" and not executemany
                and isinstance(compiled_statement, Delete)
                and compiled_statement.table.name in DELETE_TABLES
                and bool(compiled_statement._where_criteria)
                and re.search(r"\bWHERE\b", normalized, re.I) is not None,
                "NON_ALLOWLIST_SQL_REJECTED")

    def rows(db, statement, lock=False):
        return db.execute(statement.with_for_update() if lock else statement).all()

    def count(db, model, *conditions):
        return int(db.scalar(select(func.count()).select_from(model).where(*conditions)))

    # Reject unreviewed inbound foreign keys, including cross-schema dependencies.
    expected_fk = {
        ("user_emails", "user_id", "users", "id"): {"RESTRICT", "NO ACTION"},
        ("assistant_conversations", "user_id", "users", "id"): {"RESTRICT", "NO ACTION"},
        ("assistant_detection_discussions", "user_id", "users", "id"): {"RESTRICT", "NO ACTION"},
        ("assistant_detection_discussions", "conversation_id", "assistant_conversations", "id"): {"RESTRICT", "NO ACTION"},
        ("assistant_messages", "conversation_id", "assistant_conversations", "id"): {"RESTRICT", "NO ACTION"},
        ("knowledge_articles", "created_by", "users", "id"): {"SET NULL"},
        ("knowledge_articles", "updated_by", "users", "id"): {"SET NULL"},
        ("audit_logs", "actor_id", "users", "id"): {"SET NULL"},
        ("workspace_configuration", "updated_by", "users", "id"): {"SET NULL"},
    }

    def check_schema(db):
        foreign_keys = db.execute(text("""
            SELECT k.TABLE_SCHEMA, k.TABLE_NAME, k.COLUMN_NAME,
                   k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME, r.DELETE_RULE
            FROM information_schema.KEY_COLUMN_USAGE k
            JOIN information_schema.REFERENTIAL_CONSTRAINTS r
              ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA
             AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND r.TABLE_NAME=k.TABLE_NAME
            WHERE k.REFERENCED_TABLE_SCHEMA=DATABASE()
              AND k.REFERENCED_TABLE_NAME IN
                  ('users','assistant_conversations','assistant_messages',
                   'assistant_detection_discussions','user_emails','knowledge_articles')
        """)).all()
        seen = set()
        for schema, table, column, parent, parent_column, delete_rule in foreign_keys:
            key = (table, column, parent, parent_column)
            require(schema == "agriscan" and key in expected_fk, "UNKNOWN_INBOUND_FOREIGN_KEY")
            require(delete_rule in expected_fk[key], "UNEXPECTED_FOREIGN_KEY_DELETE_RULE")
            seen.add(key)
        require(seen == set(expected_fk), "EXPECTED_FOREIGN_KEY_MISSING")
        trigger_count = db.scalar(text("""
            SELECT COUNT(*) FROM information_schema.TRIGGERS
            WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE IN
              ('users','assistant_conversations','assistant_messages',
               'assistant_detection_discussions','user_emails','knowledge_articles')
        """))
        require(trigger_count == 0, "UNREVIEWED_DELETE_TABLE_TRIGGER")
        require(db.scalar(text("SELECT @@foreign_key_checks")) == 1, "FOREIGN_KEYS_DISABLED")

    preserved_models = {
        "plots": Plot, "plot_details": PlotDetails, "detections": Detection,
        "detection_predictions": DetectionPrediction, "workspace_configuration": WorkspaceConfiguration,
        "model_artifacts": ModelArtifact, "app_meta": AppMeta,
        "revoked_tokens": RevokedToken, "email_challenges": EmailChallenge,
    }
    report = {"run_id": RUN, "mode": "apply" if apply else "preview",
              "qa_user_ids": list(USER_IDS), "article_id": ARTICLE_ID}
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            try:
                require(db.scalar(text("SELECT DATABASE()")) == "agriscan", "WRONG_CONNECTED_SCHEMA")
                check_schema(db)
                # User X-locks in apply block new FK-owned children during revalidation.
                users = rows(db, select(User.id, User.username, User.role, User.is_active)
                             .where(or_(User.id.in_(USER_IDS), User.username.in_(tuple(USERS))))
                             .order_by(User.id), apply)
                require(len(users) == 3, "QA_USER_ALLOWLIST_COUNT_MISMATCH")
                require({row.username: row.id for row in users} == USERS
                        and all(row.role == "member" for row in users), "QA_USER_IDENTITY_OR_ROLE_MISMATCH")
                managed_id = db.scalar(select(AppMeta.value).where(AppMeta.key == "managed_admin_id"))
                require(managed_id and managed_id not in USER_IDS, "MANAGED_ADMIN_IS_NOT_PROTECTED")
                admins = rows(db, select(User.id, User.username, User.role, User.is_active)
                              .where(User.id == managed_id))
                require(len(admins) == 1 and admins[0].username == env["ADMIN_USERNAME"]
                        and admins[0].role == "admin" and admins[0].is_active,
                        "MANAGED_ADMIN_IDENTITY_OR_STATE_MISMATCH")
                report["managed_admin_id"] = managed_id
                articles = rows(db, select(KnowledgeArticle.id, KnowledgeArticle.title, KnowledgeArticle.status)
                                .where(KnowledgeArticle.id == ARTICLE_ID), apply)
                require(len(articles) == 1 and articles[0].title.startswith(RUN)
                        and articles[0].status == "archived", "AUTHORIZED_ARCHIVED_ARTICLE_MISMATCH")
                # This exact article may have been created by the protected admin.
                conversations = rows(db, select(Conversation.id, Conversation.user_id)
                                     .where(Conversation.user_id.in_(USER_IDS)).order_by(Conversation.id), apply)
                conversation_owners = {row.id: row.user_id for row in conversations}
                conversation_ids = tuple(conversation_owners)
                discussions = rows(db, select(DetectionDiscussion.user_id, DetectionDiscussion.detection_id,
                                               DetectionDiscussion.conversation_id)
                                   .where(or_(DetectionDiscussion.user_id.in_(USER_IDS),
                                              DetectionDiscussion.conversation_id.in_(conversation_ids))), apply)
                require(all(row.user_id in USER_IDS and row.conversation_id in conversation_owners
                            and conversation_owners[row.conversation_id] == row.user_id for row in discussions),
                        "CROSS_USER_DISCUSSION_REFERENCE")
                messages = rows(db, select(ChatMessage.id)
                                .where(ChatMessage.conversation_id.in_(conversation_ids)).order_by(ChatMessage.id), apply)
                emails = rows(db, select(UserEmail.user_id).where(UserEmail.user_id.in_(USER_IDS)), apply)
                other_articles = rows(db, select(KnowledgeArticle.id).where(
                    KnowledgeArticle.id != ARTICLE_ID,
                    or_(KnowledgeArticle.created_by.in_(USER_IDS), KnowledgeArticle.updated_by.in_(USER_IDS))), apply)
                require(not other_articles, "OTHER_ARTICLES_REFERENCE_QA_USERS")
                configs = rows(db, select(WorkspaceConfiguration.id)
                               .where(WorkspaceConfiguration.updated_by.in_(USER_IDS)), apply)
                require(not configs, "WORKSPACE_CONFIGURATION_REFERENCES_QA_USERS")
                # Locking current read captures every QA actor row after acquiring user locks.
                related_audits = rows(db, select(AuditLog.id).where(AuditLog.actor_id.in_(USER_IDS)), apply)
                audit_ids = set(db.scalars(select(AuditLog.id)).all())
                all_article_ids = set(db.scalars(select(KnowledgeArticle.id)).all())
                other_user_ids = set(db.scalars(select(User.id).where(User.id.not_in(USER_IDS))).all())
                preserved_counts = {name: count(db, model) for name, model in preserved_models.items()}
                challenge_count = int(db.scalar(select(func.count()).select_from(EmailChallenge)
                    .join(UserEmail, UserEmail.email == EmailChallenge.email).where(UserEmail.user_id.in_(USER_IDS))))
                expected = {"assistant_detection_discussions": len(discussions), "assistant_messages": len(messages),
                            "assistant_conversations": len(conversations), "user_emails": len(emails),
                            "knowledge_articles": 1, "users": 3}
                report.update({"planned_delete_counts": expected,
                    "conversation_ids": list(conversation_ids), "message_ids": [row.id for row in messages],
                    "discussion_ids": [{"user_id": row.user_id, "detection_id": row.detection_id} for row in discussions],
                    "protected_counts": preserved_counts, "other_users_preserved_count": len(other_user_ids),
                    "other_conversations_preserved_count": count(db, Conversation, Conversation.user_id.not_in(USER_IDS)),
                    "qa_email_challenges_preserved_count": challenge_count,
                    "audit_rows_preserved_count": len(audit_ids),
                    "audit_actor_ids_expected_set_null_count": len(related_audits),
                    "audit_ids_expected_set_null": [row.id for row in related_audits]})
                if not apply:
                    report["status"] = "preview_only_no_database_writes"
                    db.rollback()
                    return report
                # Repeat schema/FK checks after the target rows/tables are locked.
                check_schema(db)
                deletes = [
                    (DetectionDiscussion, DetectionDiscussion.user_id.in_(USER_IDS)),
                    (ChatMessage, ChatMessage.conversation_id.in_(conversation_ids)),
                    (Conversation, Conversation.id.in_(conversation_ids)),
                    (UserEmail, UserEmail.user_id.in_(USER_IDS)),
                    (KnowledgeArticle, KnowledgeArticle.id == ARTICLE_ID),
                    (User, User.id.in_(USER_IDS)),
                ]
                actual = {}
                for model, predicate in deletes:
                    result = db.execute(delete(model).where(predicate).execution_options(synchronize_session=False))
                    actual[model.__tablename__] = result.rowcount
                    require(result.rowcount == expected[model.__tablename__], "DELETE_ROWCOUNT_MISMATCH")
                require(set(db.scalars(select(User.id)).all()) == other_user_ids, "OTHER_USERS_CHANGED")
                require(set(db.scalars(select(KnowledgeArticle.id)).all()) == all_article_ids - {ARTICLE_ID},
                        "OTHER_ARTICLES_CHANGED")
                require(set(db.scalars(select(AuditLog.id)).all()) == audit_ids, "AUDIT_ROWS_CHANGED")
                null_audits = rows(db, select(AuditLog.id, AuditLog.actor_id)
                                  .where(AuditLog.id.in_([row.id for row in related_audits])))
                require(len(null_audits) == len(related_audits)
                        and all(row.actor_id is None for row in null_audits), "AUDIT_SET_NULL_MISMATCH")
                require(all(count(db, model) == preserved_counts[name]
                            for name, model in preserved_models.items()), "PROTECTED_TABLE_COUNTS_CHANGED")
                require(db.scalar(select(AppMeta.value).where(AppMeta.key == "managed_admin_id")) == managed_id,
                        "MANAGED_ADMIN_POINTER_CHANGED")
                report.update({"actual_delete_counts": actual,
                               "audit_actor_ids_set_null_count": len(null_audits),
                               "status": "applied_atomic_transaction"})
                db.commit()  # The only commit; no API calls, migrations, filesystem deletion or audit deletion.
                return report
            except BaseException:
                db.rollback()
                raise
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the reviewed allowlist cleanup")
    parser.add_argument("--confirm-run", default=None)
    args = parser.parse_args()
    mode = "apply" if args.apply else "preview"
    try:
        require((args.apply and args.confirm_run == RUN)
                or (not args.apply and args.confirm_run is None), "EXPLICIT_APPLY_CONFIRMATION_REQUIRED")
        report = execute_cleanup(args.apply)
    except Exception as error:
        status = ("aborted_no_commit" if isinstance(error, SafetyAbort)
                  else "aborted_rollback_requested_commit_outcome_unconfirmed" if args.apply
                  else "aborted_preview_no_dml")
        report = {"run_id": RUN, "mode": mode, "status": status,
                  "error_type": type(error).__name__,
                  "reason_code": str(error) if isinstance(error, SafetyAbort) else "DATABASE_OR_RUNTIME_ERROR_REDACTED"}
        emit_report(report)
        return 1
    return 0 if emit_report(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())

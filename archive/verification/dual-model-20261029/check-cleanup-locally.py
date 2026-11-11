"""Synthetic local helper checks only; no production, network, app config or credentials."""
import importlib.util
import json
from pathlib import Path
import tempfile
from datetime import datetime

from sqlalchemy import MetaData, Table, Column, String, Integer, Text, DateTime, Float, JSON, Boolean, ForeignKey, create_engine, select, update, insert

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cleanup_qa_tested', ROOT / 'cleanup-qa-server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
meta = MetaData()
U = Table('users', meta, Column('id', String, primary_key=True), Column('username', String), Column('role', String), Column('is_active', Boolean))
P = Table('plots', meta, Column('id', String, primary_key=True), Column('owner_id', String, ForeignKey('users.id')), Column('name', String), Column('crop', String), Column('area', Float), Column('location', String), Column('manager', String))
PD = Table('plot_details', meta, Column('plot_id', String, ForeignKey('plots.id'), primary_key=True), Column('cover_filename', String), Column('latitude', Float), Column('longitude', Float))
D = Table('detections', meta, Column('id', String, primary_key=True), Column('owner_id', String, ForeignKey('users.id')), Column('plot_id', String, ForeignKey('plots.id')), Column('name', String), Column('note', Text), Column('image_url', String), Column('is_demo', Boolean))
DP = Table('detection_predictions', meta, Column('detection_id', String, ForeignKey('detections.id'), primary_key=True), Column('model', JSON))
C = Table('assistant_conversations', meta, Column('id', String, primary_key=True), Column('user_id', String, ForeignKey('users.id')), Column('title', String), Column('busy_until', DateTime))
M = Table('assistant_messages', meta, Column('id', Integer, primary_key=True), Column('conversation_id', String, ForeignKey('assistant_conversations.id')), Column('role', String), Column('content', Text))
DD = Table('assistant_detection_discussions', meta, Column('user_id', String, ForeignKey('users.id'), primary_key=True), Column('detection_id', String, primary_key=True), Column('conversation_id', String, ForeignKey('assistant_conversations.id')))
A = Table('audit_logs', meta, Column('id', String, primary_key=True), Column('actor_id', String, ForeignKey('users.id')), Column('actor_name', String), Column('action', String), Column('resource_type', String), Column('resource_id', String), Column('summary', Text), Column('created_at', DateTime))
V = Table('alembic_version', meta, Column('version_num', String, primary_key=True))
W = Table('workspace_configuration', meta, Column('id', String, primary_key=True), Column('version', Integer), Column('data', JSON))
engine = create_engine('sqlite://')
meta.create_all(engine)
owner, other, qa_id, real_id, plot_id, chat_id, hello_id = [str(i)*32 for i in range(1,8)]
tag = 'QA-BACKGROUND-SYNTHETIC-20261029'
plan = {'run_tag': tag, 'expected_current': '/srv/agriscan/releases/release-synthetic-only', 'owner_id': owner,
        'expected_configuration_version': 7, 'expected_configuration_sha256': 'a'*64,
        'detections': [{'id': qa_id, 'name': 'QA-leaf.png', 'note': tag, 'image_url': '/api/uploads/'+'8'*32+'.jpg',
                        'source_image_sha256': 'a'*64, 'conversation_id': chat_id}],
        'plots': [{'id': plot_id, 'name': tag+'plot', 'crop': '玉米', 'area': 1.25, 'location': 'synthetic',
                   'manager': 'QA', 'cover_filename': None, 'cover_sha256': None}]}
with engine.begin() as conn:
    conn.execute(U.insert(), [{'id': owner, 'username': 'synthetic-admin', 'role': 'admin', 'is_active': True}, {'id': other, 'username': 'synthetic-real-user', 'role': 'user', 'is_active': True}])
    conn.execute(P.insert(), {'id': plot_id, 'owner_id': owner, 'name': tag+'plot', 'crop': '玉米', 'area': 1.25, 'location': 'synthetic', 'manager': 'QA'})
    conn.execute(PD.insert(), {'plot_id': plot_id, 'cover_filename': None})
    conn.execute(D.insert(), [{'id': qa_id, 'owner_id': owner, 'plot_id': plot_id, 'name': 'QA-leaf.png', 'note': tag, 'image_url': plan['detections'][0]['image_url'], 'is_demo': False}, {'id': real_id, 'owner_id': owner, 'plot_id': None, 'name': '1000032196.png', 'note': 'synthetic normal data must survive', 'image_url': '/api/uploads/'+'9'*32+'.jpg', 'is_demo': False}])
    conn.execute(DP.insert(), {'detection_id': qa_id, 'model': {'synthetic': True}})
    conn.execute(C.insert(), [{'id': chat_id, 'user_id': owner, 'title': 'QA-leaf.png', 'busy_until': datetime(2000,1,1)}, {'id': hello_id, 'user_id': owner, 'title': '你好', 'busy_until': datetime(2000,1,1)}])
    conn.execute(DD.insert(), {'user_id': owner, 'detection_id': qa_id, 'conversation_id': chat_id})
    conn.execute(M.insert(), [{'id': 1, 'conversation_id': chat_id, 'role': 'user', 'content': tag+' QA-leaf.png'}, {'id': 2, 'conversation_id': chat_id, 'role': 'assistant', 'content': 'synthetic answer'}, {'id': 3, 'conversation_id': hello_id, 'role': 'user', 'content': '你好'}])
    conn.execute(V.insert(), {'version_num': '20261029_06'})
    conn.execute(W.insert(), {'id': 'workspace', 'version': 7, 'data': {'synthetic': True, 'real_user_edit_preserved': True}})
    conn.execute(A.insert(), {'id': 'b'*32, 'actor_id': owner, 'actor_name': 'synthetic-admin', 'action': 'create', 'resource_type': 'plot', 'resource_id': plot_id, 'summary': 'QA creation audit must remain', 'created_at': datetime(2026,1,1)})
cases=[]
with engine.connect() as conn:
    plan['expected_configuration_sha256'] = m.runtime_state(conn, meta.tables)['configuration_sha256']
m.validate_plan(plan); cases.append('strict exact IDs/run tag/source image SHA plan validation')
with engine.begin() as conn:
    qa, files, scopes = m.collect(conn, meta.tables, plan, lock=True)
    assert len(qa['detections'])==1 and len(qa['assistant_messages'])==2 and files=={'8'*32+'.jpg':'a'*64}
    before=m.fingerprints(conn, meta.tables, scopes); state=m.runtime_state(conn,meta.tables)
    m.check_runtime_plan(state, plan)
    owner_row=dict(conn.execute(select(U).where(U.c.id==owner)).mappings().one())
    audit_ids=m.delete_exact(conn,meta.tables,qa,scopes,owner_row)
    assert m.fingerprints(conn,meta.tables,scopes,audit_ids)==before
    assert m.runtime_state(conn,meta.tables)==state
    assert conn.execute(select(D.c.name)).scalars().all()==['1000032196.png']
    assert conn.execute(select(C.c.title)).scalars().all()==['你好']
    assert conn.execute(select(A.c.id)).scalars().all().__len__()==3
    cases.append('exact QA deletion preserves dynamic non-QA rows, own real record, hello chat, accounts, user-edited v7 and existing audits')
    conn.rollback()
with engine.begin() as conn:
    conn.execute(update(D).where(D.c.id==qa_id).values(owner_id=other))
    try: m.collect(conn,meta.tables,plan,lock=True)
    except m.Refused as error: assert str(error) in {'detection_owner_changed', 'plot_has_non_qa_detections'}
    else: raise AssertionError('foreign owner was accepted')
    cases.append('foreign ownership rejects cleanup before deletion')
    conn.rollback()
with engine.begin() as conn:
    conn.execute(update(D).where(D.c.id==real_id).values(plot_id=plot_id))
    try: m.collect(conn,meta.tables,plan,lock=True)
    except m.Refused as error: assert str(error)=='plot_has_non_qa_detections'
    else: raise AssertionError('non QA plot reference accepted')
    cases.append('new real detection linked to QA plot blocks cleanup rather than detach/delete it')
    conn.rollback()
with engine.begin() as conn:
    conn.execute(update(C).where(C.c.id==chat_id).values(busy_until=datetime(2100,1,1)))
    try: m.collect(conn,meta.tables,plan,lock=True)
    except m.Refused as error: assert str(error)=='qa_conversation_busy'
    else: raise AssertionError('active reply accepted')
    cases.append('active QA conversation blocks cleanup')
    conn.rollback()
with tempfile.TemporaryDirectory() as temporary:
    directory=Path(temporary);photo=directory/('8'*32+'.jpg');photo.write_bytes(b'synthetic ONNX input JPEG bytes')
    assert m.checked_file(directory,photo.name,m.file_sha(photo))==photo
    try: m.checked_file(directory,photo.name,'a'*64)
    except m.Refused as error: assert str(error)=='qa_photo_sha_changed'
    else: raise AssertionError('wrong source SHA accepted')
    cases.append('source image hash must match before backup/delete')
changed={**plan,'detections':[{**plan['detections'][0],'note':'ordinary note'}]}
try:m.validate_plan(changed)
except m.Refused:pass
else:raise AssertionError('untagged note accepted')
cases.append('untagged/wide scope rejected')
with engine.connect() as conn:
    state = m.runtime_state(conn,meta.tables)
    for changed in ({**plan,'expected_configuration_version':6}, {**plan,'expected_configuration_sha256':'0'*64}):
        try:m.check_runtime_plan(state,changed)
        except m.Refused as error:assert str(error)=='configuration_baseline_changed'
        else:raise AssertionError('stale config baseline accepted')
cases.append('stale version or checksum refuses cleanup without restoring or modifying newer user configuration')
report={'status':'passed','production_network_called':False,'private_environment_read':False,'cases':cases}
(ROOT/'cleanup-helper-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','cases':len(cases),'production_network_called':False}))
engine.dispose()

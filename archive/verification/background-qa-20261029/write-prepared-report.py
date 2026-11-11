import ast,hashlib,json
from pathlib import Path
folder=Path(__file__).resolve().parent
files={}
for name in ('qa-evidence-server.py','runtime-memory-server.py','read-qa-local.py','boundary-probe-server.py','read-boundary-local.py'):
    content=(folder/name).read_bytes();ast.parse(content.decode('utf-8'));files[name]={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
evidence=json.loads((folder/'local-evidence-checks.json').read_text());boundary=json.loads((folder/'local-boundary-checks.json').read_text())
report={'status':'prepared_local_only','run_tag':'QA-BACKGROUND-20261029-1814','files':files,
 'checks':{'synthetic_evidence_cases':len(evidence['cases']),'synthetic_boundary_cases':len(boundary['cases']),'private_json_acl':'passed real local write/read with current user SID and SYSTEM only; SID strings prefixed by * for icacls'},
 'gates':{'default_wrappers_execute_ssh':False,'evidence_requires_explicit_expected_owner_id':True,'evidence_foreign_or_external_associations':'refuse',
 'boundary_requires_private_admin_handoff_and_explicit_read_server':True,'existing_reports_overwritten':False},
 'evidence_scope':['Exact fixed run tag in detection name/note or plot name/location','Only expected owner and exclusive linked QA conversations','Normalized JPEG hashes without returning image bytes','SQL source-marker verification without selecting chat content','Latest current release/schema/configuration version and canonical SQL row SHA'],
 'runtime_scope':['Systemd PID/NRestarts/InvocationID/MemoryCurrent/MemoryPeak/MemoryMax','Cgroup memory.current/peak/max/events including OOM counters','Public health fields and before/after schema/configuration SHA; no user rows or private env'],
 'boundary_scope':['Normal public DNS and trusted TLS, redirects disabled','Only latest other-owned non-demo detection metadata stays in memory','Personal detail/image GETs must return 404, response bodies are not read','No foreign ID, filename, name, note, image or chat is returned in report','No foreign records means explicit skip','Fresh CLI login is normally logged out; this may add only its own token revocation row'],
 'agent_executed_production':False,'agent_read_real_credentials':False,'agent_ran_cleanup':False,'frozen_app_sources_modified':False,
 'local_acl_incident':{'first_parent_runtime_report_empty_file_preserved':True,'local_acl_repaired':True,'reason':'icacls literal SID required an asterisk prefix; fixed before local synthetic regression','parent_was_told_new_remote_read_output_is_needed':True}}
(folder/'prepared-readiness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'scripts':len(files),'synthetic_checks':len(evidence['cases'])+len(boundary['cases']),'agent_executed_production':False}))

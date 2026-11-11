import json,socket
from pathlib import Path
folder=Path(__file__).resolve().parent
events=json.loads((folder/'events.json').read_text())
assert all(set(row)=={'method','path','fields','synthetic_only'} for row in events)
counts={path:sum(row['path']==path for row in events) for path in sorted({row['path'] for row in events})}
closed=[]
for port in (18941,18942):
    with socket.socket() as client:
        assert client.connect_ex(('127.0.0.1',port))!=0
        closed.append(port)
report={'status':'passed','method':'CUA clicks/fill against current mobile source with an isolated synthetic HTTP contract fixture',
 'cases':['registration disabled still allows the public forgot-password page',
 'sending code disables the email, proof fields, submit and header navigation',
 'fixed generic send response and sixty-second cooldown survive editing the email',
 'mismatched passwords do not submit a reset request',
 'wrong synthetic code restores the form with retry feedback',
 'synthetic reset success clears password/code and requires explicit return to login',
 'self-email section starts collapsed and marks the historical email as unverified',
 'binding send and verification have real disabled loading states',
 'wrong binding proof retains the original email and current login',
 'successful synthetic binding shows verified status and clears password/code',
 'logout while binding is pending clears the form and cannot receive its late result',
 'final fixed reset error is visible without provider OTP or password details',
 'browser back while reset is pending leaves the next login page clean',
 'final browser console has no errors'],
 'final_source_tested':True,'http_request_counts':counts,'production_network_called':False,'smtp_mail_sent':False,
 'real_account_created':False,'real_credential_changed':False,'native_android_runtime_tested':False,
 'cleanup':{'fixture_ports_closed':closed,'temporary_browser_tab_closed':True,'persisted_passwords_or_codes':False},
 'limits':['The HTTP fixture validates UI interactions and contract shape, not real mail delivery or backend password-reset correctness.','Native Android runtime is left to the user.']}
(folder/'browser-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'browser_cases':len(report['cases']),'ports_closed':closed,'request_counts':counts}))

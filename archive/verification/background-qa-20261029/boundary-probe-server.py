"""Exact personal-API boundary probes; prints no foreign IDs, filenames or bodies."""
import base64,json,re,subprocess
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler,Request,build_opener
BASE='https://agriscan.ming-ai.top/agriscan/api'
class Refused(RuntimeError):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
OPENER=build_opener(NoRedirect())
def request(path,token=None,payload=None):
    headers={'Accept':'application/json','Cache-Control':'no-store'}
    if token:headers['Authorization']='Bearer '+token
    body=None
    if payload is not None:body=json.dumps(payload).encode();headers['Content-Type']='application/json'
    try:return OPENER.open(Request(BASE+path,headers=headers,data=body),timeout=20)
    except HTTPError as error:return error
def mysql(statement):
    result=subprocess.run(['mysql','--database=agriscan','--batch','--skip-column-names','--execute',statement],capture_output=True,text=True,timeout=15)
    if result.returncode:raise Refused('read_only_boundary_metadata_unavailable_'+''.join(re.findall(r'ERROR (\d+)',result.stderr)[:1]))
    return result.stdout.splitlines()
def probe(path,token):
    response=request(path,token)
    try:return {'status_code':response.code,'cache_headers':{name.lower():response.headers[name] for name in ('Cache-Control','Pragma','Expires','Vary') if response.headers.get(name)},'body_read':False}
    finally:response.close()
def execute(credentials):
    token=None;report={'status':'refused','business_data_mutations':False,'foreign_metadata_or_body_returned':False}
    try:
        response=request('/auth/login',payload={'username':credentials['username'],'password':credentials['password']})
        try:
            if response.code!=200:raise Refused('private_admin_login_failed')
            login=json.load(response)
        finally:response.close()
        if isinstance(login.get('access_token'),str):token=login['access_token']
        if login.get('user',{}).get('role')!='admin' or not token:raise Refused('active_admin_login_required')
        username=base64.b64encode(login['user']['username'].encode()).decode()
        owner=mysql("SELECT id FROM users WHERE BINARY username=FROM_BASE64('"+username+"') AND role='admin' AND is_active=1 LIMIT 2;")
        if len(owner)!=1 or not re.fullmatch(r'[0-9a-f]{32}',owner[0]):raise Refused('exact_admin_identity_unavailable')
        # Fetch only the two fields needed for the forbidden GETs, never names or notes.
        rows=mysql("SELECT id,COALESCE(image_url,'') FROM detections WHERE owner_id IS NOT NULL AND owner_id<>'"+owner[0]+"' AND is_demo=0 ORDER BY created_at DESC,id DESC LIMIT 1;")
        if not rows:
            report.update(status='skipped',reason='no_foreign_owned_detection_exists',foreign_data_created=False)
            return report
        fields=rows[0].split('\t')
        if len(fields)!=2 or not re.fullmatch(r'[0-9a-f]{32}',fields[0]):raise Refused('foreign_boundary_metadata_shape')
        detail=probe('/detections/'+fields[0],token)
        checks={'personal_record_detail':detail}
        if re.fullmatch(r'/api/uploads/[0-9a-f]{32}\.jpg',fields[1]):checks['personal_record_image']=probe(fields[1].removeprefix('/api'),token)
        else:checks['personal_record_image']={'status':'skipped','reason':'no_canonical_private_image_path','body_read':False}
        report.update(status='passed' if detail['status_code']==404 and checks['personal_record_image'].get('status_code',404)==404 else 'failed',checks=checks,
          expected_status=404,public_dns_and_trusted_tls=True,redirects_followed=False,foreign_conversations_requested=False)
    except Refused as error:report.update(status='refused',reason=str(error))
    except Exception:report.update(status='refused',reason='private_boundary_probe_unavailable')
    finally:
        # Revoke only the fresh CLI token; no existing user session is logged out.
        if token:
            try:
                response=request('/auth/logout',token,payload={});report['fresh_cli_session_logout_status']=response.code;response.close()
            except Exception:report['fresh_cli_session_logout_status']='unconfirmed'
        report['normal_auth_endpoints_only']=['login','logout'] if token else ['login']
        report['auth_logout_may_append_own_revocation_row']=bool(token)
    return report
def main():
    # Local wrapper injects this one in-memory dict through SSH stdin, never argv/env/disk.
    report=execute(_PRIVATE_INPUT)
    print('RESULT '+json.dumps(report));return 0 if report['status'] in {'passed','skipped'} else 1
if __name__=='__main__':raise SystemExit(main())

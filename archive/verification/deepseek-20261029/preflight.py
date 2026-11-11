"""One-time provider preflight; the credential arrives only through stdin."""
import base64
import io
import json
from pathlib import Path
import sys
import time
import httpx
from PIL import Image, ImageDraw

folder = Path('.runtime/deepseek-20261029')
folder.mkdir(parents=True, exist_ok=True)
report = {'provider':'DeepSeek','base_url':'https://api.deepseek.com',
          'tls_verification':True,'configuration_saved':False,'checks':[]}
print('READY_FOR_PRIVATE_INPUT',flush=True)
key = sys.stdin.readline().strip()
if not key or len(key)>4096:
    raise SystemExit('Credential input missing or invalid.')
def save():
    (folder/'provider-preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def result(response):
    if response.status_code != 200:
        try:
            error = response.json().get('error',{})
            code = str(error.get('code',''))
        except Exception:
            code = ''
        allowed = {'invalid_api_key','authentication_error','insufficient_balance','insufficient_quota','model_not_found'}
        return {'ok':False,'http_status':response.status_code,'code':code if code in allowed else 'provider_error'}
    try:
        data = response.json()
        content = data['choices'][0]['message'].get('content')
        return {'ok':isinstance(content,str) and bool(content.strip()),'http_status':200,
                'content':content[:200] if isinstance(content,str) and key not in content else '',
                'model':data.get('model'),'usage':data.get('usage',{})}
    except Exception:
        return {'ok':False,'http_status':200,'code':'invalid_response'}

try:
    with httpx.Client(base_url='https://api.deepseek.com',headers={'Authorization':'Bearer '+key},
                      trust_env=False,timeout=60,follow_redirects=False) as client:
        started=time.monotonic()
        models = client.get('/models')
        report['catalog_status']=models.status_code
        if models.status_code != 200:
            report['status']='failed'
            report['failure_stage']='catalog'
            report['provider_error']=result(models)
            save()
            print(json.dumps({'status':'failed','stage':'catalog','http_status':models.status_code}),flush=True)
            sys.exit(1)
        rows=models.json().get('data',[])
        report['models']=[{'id':row.get('id'),'input_modalities':row.get('input_modalities')} for row in rows]
        available={row.get('id') for row in rows}
        model='deepseek-flash' if 'deepseek-flash' in available else next(
            (row['id'] for row in rows if 'image' in (row.get('input_modalities') or [])),
            'deepseek-chat' if 'deepseek-chat' in available else None)
        if not model:
            raise RuntimeError('No usable model identifier returned.')
        report['selected_model']=model
        text = client.post('/chat/completions',json={'model':model,'max_tokens':64,
            'messages':[{'role':'user','content':'请仅回复四个汉字：连接成功'}]})
        report['text']=result(text)
        if report['text']['ok']:
            image=Image.new('RGB',(160,160),'white')
            ImageDraw.Draw(image).rectangle((20,20,140,140),fill=(230,20,20))
            output=io.BytesIO()
            image.save(output,format='PNG')
            encoded=base64.b64encode(output.getvalue()).decode()
            vision=client.post('/chat/completions',json={'model':model,'max_tokens':64,
                'messages':[{'role':'user','content':[
                    {'type':'text','text':'图片正中央方块是什么颜色？只用一个英文颜色单词回答。'},
                    {'type':'image_url','image_url':{'url':'data:image/png;base64,'+encoded}}]}]})
            report['vision']=result(vision)
            report['vision']['color_recognized']='red' in report['vision'].get('content','').lower()
            report['vision']['ok']=report['vision']['ok'] and report['vision']['color_recognized']
        report['elapsed_ms']=round((time.monotonic()-started)*1000)
        report['status']='passed' if report.get('text',{}).get('ok') and report.get('vision',{}).get('ok') else 'failed'
        save()
        print(json.dumps(report,ensure_ascii=False),flush=True)
except Exception as error:
    report['status']='failed'
    report['error_type']=type(error).__name__
    save()
    print(json.dumps({'status':'failed','error_type':type(error).__name__}),flush=True)
    sys.exit(1)
finally:
    key=None

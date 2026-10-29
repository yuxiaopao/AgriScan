"""Personal workspace data must never cross authenticated account boundaries."""
from fnmatch import fnmatch
import pytest
from sqlalchemy import select

from app.assistant import Conversation, ChatMessage
from app.db import Detection, Plot, User
from app.detection_assistant import DetectionDiscussion
from test_api import auth, client, picture
from test_media import media_client, post_video, video
from test_assistant import fake_provider


def account_headers(client, username):
    credentials = {'username': username, 'name': username, 'password': 'isolated-test-password'}
    assert client.post('/api/auth/register', json=credentials).status_code == 201
    response = client.post('/api/auth/login', json=credentials)
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def upload_sample(client, headers, name='private-a.png', **fields):
    response = client.post('/api/detections', headers=headers,
                           data={'crop': '番茄', **fields},
                           files={'file': (name, picture(), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()


def account_id(client,headers):
    username=client.get('/api/auth/me',headers=headers).json()['username']
    with client.app.state.session() as db:
        return db.scalar(select(User.id).where(User.username==username))


def test_member_detection_list_is_private(client):
    owner = account_headers(client, 'isolation_a')
    outsider = account_headers(client, 'isolation_b')
    sample = upload_sample(client, owner)
    response = client.get('/api/detections', headers=outsider)
    assert response.status_code == 200
    assert sample['id'] not in {row['id'] for row in response.json()}, 'B must not see A detection in personal list'


def test_member_cannot_read_another_accounts_detection_or_photo(client):
    owner = account_headers(client, 'isolation_a')
    outsider = account_headers(client, 'isolation_b')
    sample = upload_sample(client, owner)
    assert client.get('/api/detections/' + sample['id'], headers=outsider).status_code == 404
    assert client.get(sample['image_url'], headers=outsider).status_code == 404


def create_plot(client, headers, crop='番茄', name='个人地块'):
    response = client.post('/api/plots', headers=headers,
                           json={'name':name,'crop':crop,'area':2,'location':'测试位置','manager':'测试负责人'})
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_member_and_admin_personal_views_do_not_include_legacy_samples(client):
    for headers in [account_headers(client,'empty_member'),auth(client)]:
        assert client.get('/api/detections',headers=headers).json() == []
        assert client.get('/api/plots',headers=headers).json() == []
        dashboard=client.get('/api/dashboard',headers=headers).json()
        assert dashboard['stats']=={'total':0,'healthy':0,'attention':0,'pending':0}
        assert dashboard['distribution']==[] and dashboard['recent']==[]
        assert not any(day['total'] for day in dashboard['trend'])
        assert client.get('/api/detections/demo-001',headers=headers).status_code==404


def test_owner_filter_precedes_search_status_crop_and_personal_export_source(client):
    owner=account_headers(client,'filter_owner')
    outsider=account_headers(client,'filter_outsider')
    a=upload_sample(client,owner,name='shared-search-a.png')
    b=upload_sample(client,outsider,name='shared-search-b.png')
    for headers, expected in [(owner,a),(outsider,b)]:
        for params in [{},{'search':'shared-search'},{'crop':'番茄'},{'status':'awaiting_model'},
                       {'search':'shared-search','crop':'番茄','status':'awaiting_model'}]:
            rows=client.get('/api/detections',headers=headers,params=params).json()
            assert [row['id'] for row in rows]==[expected['id']]
            # Desktop personal CSV export is derived from these filtered rows.
            assert {row['name'] for row in rows}=={expected['name']}
    assert client.get('/api/detections',headers=auth(client)).json()==[]


def test_dashboard_cache_and_all_aggregations_are_scoped_to_owner_and_days(client):
    a_headers=account_headers(client,'cache_a')
    b_headers=account_headers(client,'cache_b')
    a=upload_sample(client,a_headers,name='cache-a.png')
    b=[upload_sample(client,b_headers,name=f'cache-b-{index}.png',crop='玉米') for index in range(2)]
    class InMemoryRedis:
        def __init__(self):self.values={}
        def get(self,key):return self.values.get(key)
        def setex(self,key,ttl,value):self.values[key]=value
        def delete(self,*keys):
            for key in keys:self.values.pop(key,None)
        def scan_iter(self,match,count=128):return iter([key for key in self.values if fnmatch(key,match)])
        def close(self):pass
    client.app.state.cache.client=InMemoryRedis()
    # Alternate warm cache reads; a globally cached response must never be reused.
    for days in [7,30,7]:
        for headers,rows,crop in [(b_headers,b,'玉米'),(a_headers,[a],'番茄'),(b_headers,b,'玉米')]:
            dashboard=client.get('/api/dashboard',headers=headers,params={'days':days}).json()
            assert dashboard['stats']=={'total':len(rows),'healthy':0,'attention':0,'pending':len(rows)}
            assert len(dashboard['trend'])==days and sum(day['total'] for day in dashboard['trend'])==len(rows)
            assert [(item['name'],item['value']) for item in dashboard['distribution']]==[(crop,len(rows))]
            assert {row['id'] for row in dashboard['recent']}=={row['id'] for row in rows}


def test_members_can_manage_only_their_own_plots_and_covers(client):
    owner=account_headers(client,'plot_owner')
    outsider=account_headers(client,'plot_outsider')
    administrator=auth(client)
    plot=create_plot(client,owner)
    url='/api/plots/'+plot['id']
    assert client.get('/api/plots',headers=owner).json()[0]['id']==plot['id']
    assert client.get('/api/plots',headers=outsider).json()==[]
    assert client.get('/api/plots',headers=administrator).json()==[]
    cover=client.post(url+'/cover',headers=owner,files={'file':('cover.png',picture(),'image/png')})
    assert cover.status_code==200
    image=cover.json()['cover_url']
    assert client.get(image,headers=owner).status_code==200
    for headers in [outsider,administrator]:
        assert client.patch(url,headers=headers,json={'name':'not yours'}).status_code==404
        assert client.post(url+'/cover',headers=headers,files={'file':('other.png',picture(),'image/png')}).status_code==404
        assert client.delete(url+'/cover',headers=headers).status_code==404
        assert client.delete(url,headers=headers).status_code==404
        assert client.get(image,headers=headers).status_code==404
    changed=client.patch(url,headers=owner,json={'name':'自己的新名字'})
    assert changed.status_code==200 and changed.json()['name']=='自己的新名字'
    assert client.delete(url+'/cover',headers=owner).status_code==200
    assert client.get(image,headers=owner).status_code==404
    assert client.delete(url,headers=owner).status_code==200


def test_detection_cannot_attach_to_another_users_plot_or_delete_anothers_sample(client):
    owner=account_headers(client,'link_owner')
    outsider=account_headers(client,'link_outsider')
    plot=create_plot(client,owner)
    own=upload_sample(client,owner,plot_id=plot['id'])
    response=client.post('/api/detections',headers=outsider,data={'crop':'番茄','plot_id':plot['id']},
                         files={'file':('wrong-owner.png',picture(),'image/png')})
    assert response.status_code==404
    for headers in [outsider,auth(client)]:
        assert client.delete('/api/detections/'+own['id'],headers=headers).status_code==404
    assert client.delete('/api/detections/'+own['id'],headers=owner).status_code==200
    assert client.get(own['image_url'],headers=owner).status_code==404


def test_created_entities_receive_the_authenticated_owner_not_client_input(client):
    headers=account_headers(client,'assigned_owner')
    user_id=account_id(client,headers)
    plot=create_plot(client,headers)
    row=upload_sample(client,headers,plot_id=plot['id'],owner_id='somebody-else')
    with client.app.state.session() as db:
        assert db.get(Plot,plot['id']).owner_id==user_id
        assert db.get(Detection,row['id']).owner_id==user_id


def test_anonymous_demo_never_contains_real_or_owned_rows(client):
    owner=account_headers(client,'demo_boundary_owner')
    own=upload_sample(client,owner)
    with client.app.state.session() as db:
        db.add(Detection(id='legacy-real',name='unknown-owner.jpg',crop='番茄',plot_id=None,
                         status='healthy',result='健康',confidence=.9,is_demo=False,note='legacy unknown'))
        db.commit()
    rows=client.get('/api/detections').json()
    assert rows and all(row['is_demo'] for row in rows)
    assert own['id'] not in {row['id'] for row in rows}
    assert client.get('/api/detections/legacy-real').status_code==404
    assert client.get(own['image_url']).status_code==404
    dashboard=client.get('/api/dashboard').json()
    assert dashboard['stats']['total']==12 and all(row['is_demo'] for row in dashboard['recent'])
    for headers in [owner,auth(client)]:
        assert client.get('/api/detections/legacy-real',headers=headers).status_code==404


def test_production_anonymous_cannot_reuse_demo_cache_or_read_private_images(client):
    owner=account_headers(client,'production_owner')
    row=upload_sample(client,owner)
    assert client.get('/api/dashboard').status_code==200
    client.app.state.settings.demo_mode=False
    for path in ['/api/detections','/api/detections/'+row['id'],'/api/dashboard','/api/plots',row['image_url']]:
        assert client.get(path).status_code==401


def test_video_frames_keep_owner_and_reject_foreign_plot_before_persisting(media_client,tmp_path):
    client=media_client
    owner=account_headers(client,'video_owner')
    outsider=account_headers(client,'video_outsider')
    plot=create_plot(client,owner,crop='玉米')
    payload=video(tmp_path,frames=4,fps=2)
    denied=post_video(client,outsider,payload,plot_id=plot['id'])
    assert denied.status_code==404
    response=post_video(client,owner,payload,plot_id=plot['id'])
    assert response.status_code==200,response.text
    rows=[item['detection'] for item in response.json()['results']]
    assert rows
    owner_id=account_id(client,owner)
    with client.app.state.session() as db:
        assert {db.get(Detection,row['id']).owner_id for row in rows}=={owner_id}
    assert {row['id'] for row in client.get('/api/detections',headers=owner).json()}=={row['id'] for row in rows}
    assert client.get('/api/detections',headers=outsider).json()==[]
    assert all(client.get(row['image_url'],headers=outsider).status_code==404 for row in rows)


def test_foreign_detection_analysis_never_calls_model_even_with_existing_discussion(client,monkeypatch):
    owner=account_headers(client,'analysis_owner')
    outsider=account_headers(client,'analysis_outsider')
    own=upload_sample(client,owner)
    own_id=account_id(client,owner)
    outsider_id=account_id(client,outsider)
    # A pre-fix discussion link must not bypass the newly protected source record.
    with client.app.state.session() as db:
        chat=Conversation(user_id=outsider_id,title='old leaked discussion')
        db.add(chat);db.flush()
        db.add(ChatMessage(conversation_id=chat.id,role='assistant',content='must not be returned'))
        db.add(DetectionDiscussion(user_id=outsider_id,detection_id=own['id'],conversation_id=chat.id))
        db.commit()
    calls=[]
    monkeypatch.setattr('app.extensions.httpx.post',lambda *args,**kwargs:calls.append(kwargs))
    for headers in [outsider,auth(client)]:
        response=client.post('/api/assistant/detections/'+own['id']+'/analysis',headers=headers)
        assert response.status_code==404
        assert 'must not be returned' not in response.text
    assert calls==[]
    with client.app.state.session() as db:
        assert db.get(Detection,own['id']).owner_id==own_id


def test_admin_console_can_filter_and_export_other_owners_without_personal_bypass(client):
    a_headers=account_headers(client,'console_a')
    b_headers=account_headers(client,'console_b')
    administrator=auth(client)
    a=upload_sample(client,a_headers,name='console-private-a.png')
    b=upload_sample(client,b_headers,name='console-private-b.png')
    a_id,b_id=account_id(client,a_headers),account_id(client,b_headers)
    for owner_id,sample,username,other in [(a_id,a,'console_a',b),(b_id,b,'console_b',a)]:
        response=client.get('/api/admin/detections',headers=administrator,params={'owner_id':owner_id})
        assert response.status_code==200
        rows=response.json()['items']
        assert [row['id'] for row in rows]==[sample['id']]
        assert rows[0]['owner_id']==owner_id and rows[0]['owner_username']==username
        assert rows[0]['owner_name']==username
        assert rows[0]['image_url'].startswith('/api/admin/uploads/')
        image=client.get(rows[0]['image_url'],headers=administrator)
        assert image.status_code==200 and image.headers['content-type'].startswith('image/')
        assert client.get(rows[0]['image_url'],headers=a_headers).status_code==403
        exported=client.get('/api/admin/detections/export.csv',headers=administrator,params={'owner_id':owner_id})
        assert exported.status_code==200
        assert sample['name'] in exported.text and other['name'] not in exported.text
        assert client.get('/api/detections/'+sample['id'],headers=administrator).status_code==404
        assert client.get(sample['image_url'],headers=administrator).status_code==404
    unassigned=client.get('/api/admin/detections',headers=administrator,params={'owner_id':'unassigned'}).json()
    assert unassigned['items'] and all(row['owner_id'] is None for row in unassigned['items'])
    assert client.get('/api/detections',headers=administrator).json()==[]


def test_admin_owner_reassignment_preserves_plot_invariants_and_personal_visibility(client):
    a_headers=account_headers(client,'reassign_a')
    b_headers=account_headers(client,'reassign_b')
    administrator=auth(client)
    a_id,b_id=account_id(client,a_headers),account_id(client,b_headers)
    created=client.post('/api/admin/plots',headers=administrator,json={
        'name':'管理员为A登记','crop':'番茄','area':3,'location':'测试地块','manager':'负责人','owner_id':a_id})
    assert created.status_code==201,created.text
    plot=created.json()
    assert plot['owner_id']==a_id
    sample=upload_sample(client,a_headers,plot_id=plot['id'])
    plot_url='/api/admin/plots/'+plot['id']
    detection_url='/api/admin/detections/'+sample['id']
    assert client.patch(plot_url,headers=administrator,json={'owner_id':b_id}).status_code==409
    assert client.patch(detection_url,headers=administrator,json={'owner_id':b_id}).status_code==422
    assert client.get(detection_url,headers=administrator).json()['owner_id']==a_id
    assert client.get(plot_url,headers=administrator).json()['owner_id']==a_id
    detached=client.patch(detection_url,headers=administrator,json={'owner_id':b_id,'plot_id':None})
    assert detached.status_code==200,detached.text
    assert detached.json()['owner_id']==b_id and detached.json()['plot_id'] is None
    assert client.get('/api/detections/'+sample['id'],headers=a_headers).status_code==404
    assert client.get('/api/detections/'+sample['id'],headers=b_headers).status_code==200
    assert client.get(sample['image_url'],headers=a_headers).status_code==404
    assert client.get(sample['image_url'],headers=b_headers).status_code==200
    reassigned=client.patch(plot_url,headers=administrator,json={'owner_id':b_id})
    assert reassigned.status_code==200
    assert client.get('/api/plots',headers=a_headers).json()==[]
    assert client.get('/api/plots',headers=b_headers).json()[0]['id']==plot['id']
    assert client.delete(detection_url,headers=administrator).status_code==200
    assert client.get('/api/detections/'+sample['id'],headers=b_headers).status_code==404
    assert client.delete(plot_url,headers=administrator).status_code==200


@pytest.mark.parametrize('source_state',['foreign','unassigned','missing'])
def test_legacy_linked_conversations_require_verified_source_ownership(client,monkeypatch,source_state):
    source_owner=account_headers(client,'legacy_source_owner')
    reader=account_headers(client,'legacy_snapshot_reader')
    administrator=auth(client)
    source=upload_sample(client,source_owner)
    ordinary=client.post('/api/assistant/conversations',headers=reader).json()
    links=[]
    with client.app.state.session() as db:
        for headers in [reader,administrator]:
            user_id=account_id(client,headers)
            chat=Conversation(user_id=user_id,title='old linked snapshot')
            db.add(chat);db.flush()
            db.add(ChatMessage(conversation_id=chat.id,role='assistant',content='private source snapshot'))
            db.add(DetectionDiscussion(user_id=user_id,detection_id=source['id'],conversation_id=chat.id))
            links.append((headers,chat.id))
        if source_state=='unassigned':db.get(Detection,source['id']).owner_id=None
        elif source_state=='missing':db.delete(db.get(Detection,source['id']))
        db.commit()
    calls=fake_provider(client,monkeypatch)
    for headers,chat_id in links:
        listing=client.get('/api/assistant/conversations',headers=headers)
        assert listing.status_code==200 and chat_id not in {row['id'] for row in listing.json()}
        route='/api/assistant/conversations/'+chat_id
        response=client.get(route,headers=headers)
        assert response.status_code==404 and 'private source snapshot' not in response.text
        assert client.post(route+'/messages',headers=headers,json={'question':'请继续解读照片'}).status_code==404
    assert calls==[]
    # Independent text chats still work; no source linkage means no sample leak.
    route='/api/assistant/conversations/'+ordinary['id']
    assert client.get(route,headers=reader).status_code==200
    assert client.post(route+'/messages',headers=reader,json={'question':'巡田应该记录哪些信息？'}).status_code==200
    assert len(calls)==1


def test_linked_history_hides_after_owner_transfer_and_reappears_only_after_verified_restoration(client):
    owner=account_headers(client,'history_owner')
    other=account_headers(client,'history_new_owner')
    own_id,other_id=account_id(client,owner),account_id(client,other)
    row=upload_sample(client,owner)
    with client.app.state.session() as db:
        chat=Conversation(user_id=own_id,title='verified source history')
        db.add(chat);db.flush();chat_id=chat.id
        db.add(ChatMessage(conversation_id=chat.id,role='assistant',content='retained original analysis'))
        db.add(DetectionDiscussion(user_id=own_id,detection_id=row['id'],conversation_id=chat.id))
        db.commit()
    route='/api/assistant/conversations/'+chat_id
    assert client.get(route,headers=owner).status_code==200
    with client.app.state.session() as db:
        db.get(Detection,row['id']).owner_id=other_id;db.commit()
    assert client.get(route,headers=owner).status_code==404
    assert client.get(route,headers=other).status_code==404
    assert chat_id not in {item['id'] for item in client.get('/api/assistant/conversations',headers=owner).json()}
    with client.app.state.session() as db:
        assert db.get(Conversation,chat_id) is not None
        db.get(Detection,row['id']).owner_id=own_id;db.commit()
    restored=client.get(route,headers=owner)
    assert restored.status_code==200 and restored.json()['messages'][0]['content']=='retained original analysis'


def test_image_upload_rechecks_plot_owner_after_inference_before_persisting(client,monkeypatch):
    owner=account_headers(client,'image_race_owner')
    other=account_headers(client,'image_race_new_owner')
    other_id=account_id(client,other)
    plot=create_plot(client,owner)
    original=client.app.state.inference.predict
    def transfer_during_inference(*args,**kwargs):
        result=original(*args,**kwargs)
        with client.app.state.session() as db:
            db.get(Plot,plot['id']).owner_id=other_id;db.commit()
        return result
    monkeypatch.setattr(client.app.state.inference,'predict',transfer_during_inference)
    response=client.post('/api/detections',headers=owner,data={'crop':'番茄','plot_id':plot['id']},
                         files={'file':('race.png',picture(),'image/png')})
    assert response.status_code==404
    assert client.get('/api/detections',headers=owner).json()==[]
    assert client.get('/api/plots',headers=other).json()[0]['id']==plot['id']
    assert list(client.app.state.settings.upload_dir.iterdir())==[]


def test_video_upload_rechecks_plot_owner_after_sampling_before_persisting(media_client,tmp_path,monkeypatch):
    import app.media as media
    client=media_client
    owner=account_headers(client,'video_race_owner')
    other=account_headers(client,'video_race_new_owner')
    other_id=account_id(client,other)
    plot=create_plot(client,owner,crop='玉米')
    original=media.sample_video
    def transfer_during_sampling(*args,**kwargs):
        result=original(*args,**kwargs)
        with client.app.state.session() as db:
            db.get(Plot,plot['id']).owner_id=other_id;db.commit()
        return result
    monkeypatch.setattr(media,'sample_video',transfer_during_sampling)
    response=post_video(client,owner,video(tmp_path,frames=2,fps=1),plot_id=plot['id'])
    assert response.status_code==404
    assert client.get('/api/detections',headers=owner).json()==[]
    assert client.get('/api/plots',headers=other).json()[0]['id']==plot['id']
    assert list(client.app.state.settings.upload_dir.iterdir())==[]


def test_analysis_rechecks_detection_owner_after_model_reply_before_saving(client,monkeypatch):
    import httpx
    owner=account_headers(client,'analysis_race_owner')
    other=account_headers(client,'analysis_race_new_owner')
    own_id,other_id=account_id(client,owner),account_id(client,other)
    row=upload_sample(client,owner)
    client.app.state.settings.llm_enabled=True
    def transfer_before_reply(*args,**kwargs):
        with client.app.state.session() as db:
            db.get(Detection,row['id']).owner_id=other_id;db.commit()
        return httpx.Response(200,json={'choices':[{'message':{'content':'must not persist after reassignment'}}]},
                              request=httpx.Request('POST','https://example.com/chat/completions'))
    monkeypatch.setattr('app.extensions.httpx.post',transfer_before_reply)
    response=client.post('/api/assistant/detections/'+row['id']+'/analysis',headers=owner)
    assert response.status_code==404
    with client.app.state.session() as db:
        assert db.get(DetectionDiscussion,(own_id,row['id'])) is None
        assert not db.scalars(select(Conversation).where(Conversation.user_id==own_id)).all()

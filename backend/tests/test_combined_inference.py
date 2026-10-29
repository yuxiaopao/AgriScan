"""Independent model verification uses explicit keys, never fused probabilities."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from threading import Event

from fastapi import HTTPException
from fastapi.testclient import TestClient
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import pytest

from app.combined_inference import DetectionWithClassificationProvider, validated_mapping
from app.config import Settings
from app.db import DetectionPrediction, Detection
from app.inference import InferenceResult, create_provider, prediction_snapshot, public_prediction_model
from app.main import create_app
from test_api import picture
from test_assistant import fake_provider
from test_detection_inference import fixture_manifest
from test_media import post_frame, post_video, video
from test_user_isolation import account_headers, account_id

ROOT = Path(__file__).resolve().parents[2]
DETECTION_LABELS = json.loads((ROOT/'models/candidates/user-detect-fafc2bb3ce9e/manifest.json').read_text(encoding='utf-8'))['classes']
CLASSIFICATION_LABELS = json.loads((ROOT/'models/releases/plantvillage-yolo26m-906cf72f6bf0/manifest.json').read_text(encoding='utf-8'))['classes']
MAPPING = json.loads((ROOT/'backend/app/class_verification_mapping.json').read_text(encoding='utf-8'))


class Component:
    status = 'ready'
    def __init__(self, task, labels, result):
        self.labels = deepcopy(labels)
        self.active = {'name':'SYNTHETIC_'+task,'task':task,'onnx_sha256':task+'-hash',
                       'threshold':0.7,'class_count':len(labels),'image_size':224}
        self.supported_crops = sorted({label['crop'] for label in labels})
        self.threshold = 0.7
        self.result, self.calls = result, []
    def predict(self, path, crop=None):
        self.calls.append((path,crop))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def pair(detect_key='Apple_healthy', classify_key=None, confidence=0.93, count=1):
    classification_key = classify_key or MAPPING[detect_key]
    detection_label = next(item for item in DETECTION_LABELS if item['key']==detect_key)
    classification_label = next(item for item in CLASSIFICATION_LABELS if item['key']==classification_key)
    boxes = [{**detection_label,'confidence':0.87,'class_id':0,'bbox':[0.1,0.1,0.9,0.9]} for _ in range(count)]
    model = {'name':'detector','task':'detect','onnx_sha256':'detect-hash'}
    detected = InferenceResult('healthy' if detection_label['healthy'] else 'attention',detection_label['label'],0.87,
                               [{**detection_label,'confidence':0.87}],model,detection_label['crop'],boxes,key=detect_key)
    classified = InferenceResult('attention' if confidence<0.7 else 'healthy',
                                '置信度不足，请人工复核（候选：wrapper）',confidence,
                                [{**classification_label,'confidence':confidence}],
                                {'name':'classifier','task':'classify','onnx_sha256':'classify-hash'},
                                classification_label['crop'],key=classification_key)
    detector = Component('detect',DETECTION_LABELS,detected)
    classifier = Component('classify',CLASSIFICATION_LABELS,classified)
    return DetectionWithClassificationProvider(detector,classifier),detector,classifier


def test_explicit_mapping_covers_38_real_keys_and_ignores_order_and_display_aliases():
    assert len(MAPPING)==len(DETECTION_LABELS)==len(CLASSIFICATION_LABELS)==38
    detection,classification=validated_mapping(list(reversed(DETECTION_LABELS)),CLASSIFICATION_LABELS[9:]+CLASSIFICATION_LABELS[:9],MAPPING)
    assert MAPPING['Corn_Common_rust']=='Corn_(maize)___Common_rust_'
    assert MAPPING['Cherry_healthy']=='Cherry_(including_sour)___healthy'
    assert MAPPING['Tomato_Spider_mites_Two-spotted_spider_mite']=='Tomato___Spider_mites Two-spotted_spider_mite'
    assert detection['Apple_Cedar_apple_rust']['label'] != classification['Apple___Cedar_apple_rust']['label']
    provider,_,_=pair('Apple_Cedar_apple_rust')
    assert provider.predict(Path('leaf.jpg')).model['verification']['status']=='agree'


@pytest.mark.parametrize('problem',['missing','extra','duplicate','crop','healthy'])
def test_incomplete_or_incompatible_mapping_is_rejected_at_startup(problem):
    mapping,labels=deepcopy(MAPPING),deepcopy(CLASSIFICATION_LABELS)
    if problem=='missing': mapping.pop('Apple_healthy')
    elif problem=='extra': mapping['unknown']='unknown'
    elif problem=='duplicate': mapping['Apple_healthy']=mapping['Blueberry_healthy']
    elif problem=='crop': labels[0]['crop']='玉米'
    else: labels[0]['healthy']=True
    with pytest.raises(ValueError):
        validated_mapping(DETECTION_LABELS,labels,mapping)


@pytest.mark.parametrize('detect_key,classify_key,confidence,count,expected',[
    ('Apple_healthy','Apple___healthy',0.93,1,'agree'),
    ('Apple_healthy','Apple___Apple_scab',0.93,1,'disagree'),
    ('Apple_Apple_scab','Apple___healthy',0.93,1,'disagree'),
    ('Apple_healthy','Corn_(maize)___healthy',0.93,1,'disagree'),
    ('Apple_healthy','Apple___healthy',0.4,1,'uncertain'),
    ('Apple_healthy','Apple___healthy',0.93,2,'uncertain'),
    ('Apple_healthy','Apple___Apple_scab',0.4,2,'uncertain'),
])
def test_primary_result_is_preserved_and_independent_scores_are_never_fused(detect_key,classify_key,confidence,count,expected):
    provider,detector,classifier=pair(detect_key,classify_key,confidence,count)
    path=Path('entire-original.jpg')
    result=provider.predict(path,'苹果')
    verification=result.model['verification']
    assert verification['status']==expected and verification['scope']=='whole_image'
    assert detector.calls==[(path,'苹果')] and classifier.calls==[(path,None)]
    assert result.label==detector.result.label and result.crop==detector.result.crop
    assert result.confidence==0.87 and result.boxes==detector.result.boxes
    assert result.candidates==detector.result.candidates
    assert result.status==(detector.result.status if expected=='agree' else 'attention')
    assert verification['detection']['key']==detect_key and verification['detection']['confidence']==0.87
    classified=verification['classification']
    assert classified['confidence']==confidence and classified['key']==classify_key
    assert classified['label']==classifier.result.candidates[0]['label']
    assert '置信度不足' not in classified['label']
    assert classified['candidates']==classifier.result.candidates
    if count>1: assert '不能逐框' in verification['message']
    snapshot=prediction_snapshot(result)
    assert snapshot['verification']==verification and snapshot['boxes']==result.boxes
    assert 'boxes' not in public_prediction_model(snapshot) and public_prediction_model(snapshot)['verification']==verification


@pytest.mark.parametrize('fault',[HTTPException(503,'private path/key in provider error'),RuntimeError('private path/key in provider error')])
def test_classification_failure_is_safe_and_keeps_real_detection(fault):
    provider,detector,classifier=pair()
    classifier.result=fault
    result=provider.predict(Path('image.jpg'))
    verification=result.model['verification']
    assert verification['status']=='unavailable' and verification['classification'] is None
    assert result.status=='attention' and result.boxes==detector.result.boxes and result.label==detector.result.label
    assert 'private' not in json.dumps(verification)
    assert provider.guard.acquire(blocking=False)
    provider.guard.release()


def test_no_detection_does_not_run_classifier_and_releases_pipeline_guard():
    provider,detector,classifier=pair()
    detector.result=HTTPException(422,'no target')
    with pytest.raises(HTTPException) as error:
        provider.predict(Path('image.jpg'))
    assert error.value.status_code==422 and classifier.calls==[]
    assert provider.guard.acquire(blocking=False)
    provider.guard.release()


def test_whole_pipeline_guard_rejects_interleaving_while_classifier_is_running():
    provider,detector,classifier=pair()
    entered,release=Event(),Event()
    original=classifier.predict
    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    classifier.predict=blocked
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(provider.predict,Path('first.jpg'))
        assert entered.wait(5)
        try:
            with pytest.raises(HTTPException) as error:
                provider.predict(Path('second.jpg'))
            assert error.value.status_code==503
            assert detector.calls==[(Path('first.jpg'),None)]
        finally:
            release.set()
        assert future.result().model['verification']['status']=='agree'
    assert provider.predict(Path('third.jpg')).model['verification']['status']=='agree'


def dual_manifests(tmp_path,classification_key='Apple___Apple_scab'):
    detect_index=next(index for index,item in enumerate(DETECTION_LABELS) if item['key']=='Apple_healthy')
    primary=fixture_manifest(tmp_path/'detector',[[0,0,640,640,0.87,detect_index]],classes=DETECTION_LABELS)
    folder=tmp_path/'classifier'
    folder.mkdir()
    values=np.full((1,38),0.01/37,dtype=np.float32)
    classification_index=next(index for index,item in enumerate(CLASSIFICATION_LABELS) if item['key']==classification_key)
    values[0,classification_index]=0.99
    graph=helper.make_graph([helper.make_node('Constant',[],['output'],value=numpy_helper.from_array(values))],
                            'SYNTHETIC_VERIFIER_ONLY',[helper.make_tensor_value_info('images',TensorProto.FLOAT,[1,3,224,224])],
                            [helper.make_tensor_value_info('output',TensorProto.FLOAT,[1,38])])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=9)
    onnx.save(model,folder/'model.onnx')
    metadata={'name':'SYNTHETIC_VERIFIER_ONLY','task':'classify','validation_passed':True,'image_size':224,
              'threshold':0.7,'test_top1':0.0,'test_macro_f1':0.0,'classes':CLASSIFICATION_LABELS,
              'preprocessing':'resize-shortest-bilinear-center-crop-rgb-div255',
              'onnx_sha256':hashlib.sha256((folder/'model.onnx').read_bytes()).hexdigest()}
    secondary=folder/'manifest.json'
    secondary.write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
    return primary,secondary


def test_factory_uses_validated_onnx_loaders_and_preserves_single_model_compatibility(tmp_path):
    primary,secondary=dual_manifests(tmp_path)
    settings=Settings(model_manifest=str(primary),classification_model_manifest='')
    single=create_provider(settings)
    assert single.active['task']=='detect' and 'components' not in single.active
    combined=create_provider(replace(settings,classification_model_manifest=str(secondary)))
    assert combined.active['task']=='detect' and combined.active['test_top1'] is None
    assert combined.active['pipeline']=='detection_with_classification'
    assert [row['role'] for row in combined.active['components']]==['detection','verification']
    assert [row['task'] for row in combined.active['components']]==['detect','classify']
    assert all(row['status']=='ready' and row['onnx_sha256'] for row in combined.active['components'])
    with pytest.raises(ValueError): create_provider(replace(settings,model_manifest='',classification_model_manifest=str(secondary)))
    with pytest.raises(ValueError): create_provider(replace(settings,model_manifest=str(secondary),classification_model_manifest=str(secondary)))
    (secondary.parent/'model.onnx').write_bytes(b'invalid artifact must never load')
    with pytest.raises(ValueError,match='SHA256'):
        create_provider(replace(settings,classification_model_manifest=str(secondary)))


def test_api_snapshot_assistant_media_and_ownership_keep_independent_verification(tmp_path,monkeypatch):
    primary,secondary=dual_manifests(tmp_path)
    settings=Settings(database_url=f"sqlite:///{tmp_path/'combined.db'}",upload_dir=tmp_path/'uploads',redis_url='',
                      model_manifest=str(primary),classification_model_manifest=str(secondary),demo_mode=True,
                      admin_username='admin',admin_password='admin12345',registration_enabled=True,
                      email_verification_enabled=False,llm_enabled=False)
    with TestClient(create_app(settings)) as client:
        headers=account_headers(client,'pair_owner')
        other=account_headers(client,'pair_other')
        response=client.post('/api/detections',headers=headers,files={'file':('leaf.png',picture(),'image/png')})
        assert response.status_code==201,response.text
        row=response.json()
        verification=row['prediction_model']['verification']
        assert row['result']=='苹果健康' and row['status']=='attention' and verification['status']=='disagree'
        assert row['boxes'][0]['healthy'] is True and verification['classification']['healthy'] is False
        assert client.get('/api/detections/'+row['id'],headers=headers).json()==row
        assert client.get('/api/detections/'+row['id'],headers=other).status_code==404
        assert client.get(row['image_url'],headers=other).status_code==404
        with client.app.state.session() as db:
            stored=db.get(DetectionPrediction,row['id'])
            assert stored.model['verification']==verification and stored.model['boxes']==row['boxes']
            assert db.get(Detection,row['id']).owner_id==account_id(client,headers)
        info=client.get('/api/models',headers=headers).json()
        assert info['active']['pipeline']=='detection_with_classification' and len(info['active']['components'])==2
        calls=fake_provider(client,monkeypatch)
        assert client.post('/api/assistant/detections/'+row['id']+'/analysis',headers=other).status_code==404
        analyzed=client.post('/api/assistant/detections/'+row['id']+'/analysis',headers=headers)
        assert analyzed.status_code==200,analyzed.text
        prompt=calls[0][-1]['content'][0]['text']
        facts=json.loads(prompt.split('检测记录：',1)[1])
        assert facts['独立整图分类复核（非逐框、分数不融合）']==verification
        assert '不能仅凭主结果宣称健康' in prompt and '不能平均、相乘或融合' in prompt
        # The fake first answer contains no model label or score. A follow-up
        # must still receive the independently persisted raw classification.
        chat_id=analyzed.json()['conversation']['id']
        followup=client.post('/api/assistant/conversations/'+chat_id+'/messages',headers=headers,
                             json={'question':'分类模型的类别和原始分数是多少？'})
        assert followup.status_code==200,followup.text
        stored_summary=calls[1][1]['content']
        raw=json.loads(stored_summary.split('独立整图分类复核（整图、原始分数独立不融合）：',1)[1])
        assert raw==verification and raw['classification']['key']=='Apple___Apple_scab'
        assert raw['classification']['confidence']==verification['classification']['confidence']
        assert raw['model']['name']=='SYNTHETIC_VERIFIER_ONLY'
        preview=post_frame(client,headers)
        assert preview.status_code==200 and preview.json()['prediction_model']['verification']['status']=='disagree'
        recording=post_video(client,headers,video(tmp_path,frames=2,fps=4))
        assert recording.status_code==200,recording.text
        for item in recording.json()['results']:
            assert item['detection']['prediction_model']['verification']['scope']=='whole_image'
            assert item['detection']['status']=='attention'
            assert client.get('/api/detections/'+item['detection']['id'],headers=other).status_code==404

"""Automatic classification feeds saved species, disease facts and image to Xiaohe."""
import base64
import io
import json

from PIL import Image
import pytest

from test_api import auth, picture
from test_assistant import fake_provider
from test_inference import model_client


@pytest.mark.parametrize('probabilities,crop,label,score', [
    ((0.03, 0.02, 0.95), '玉米', '玉米健康', '95.00%'),
    ((0.05, 0.9, 0.05), '番茄', '番茄早疫病', '90.00%'),
])
def test_automatic_detection_flows_into_image_analysis_and_saved_conversation(
    tmp_path, monkeypatch, probabilities, crop, label, score,
):
    with model_client(tmp_path, probabilities) as client:
        calls = fake_provider(client, monkeypatch)
        headers = auth(client)
        uploaded = client.post('/api/detections', headers=headers, data={'note': '叶背发现小孔'},
                               files={'file': ('field-leaf.png', picture(), 'image/png')})
        assert uploaded.status_code == 201, uploaded.text
        detection = uploaded.json()
        assert detection['crop'] == crop and detection['result'] == label

        route = f"/api/assistant/detections/{detection['id']}/analysis"
        response = client.post(route, headers=headers)
        assert response.status_code == 200, response.text
        assert len(calls) == 1
        parts = calls[0][-1]['content']
        assert [part['type'] for part in parts] == ['text', 'image_url']
        prompt = parts[0]['text']
        facts = json.loads(prompt.split('检测记录：', 1)[1])
        assert facts['作物'] == detection['crop']
        assert facts['分类结果'] == detection['result']
        assert facts['分类置信度'] == detection['confidence']
        assert facts['单标签分类候选（原始分数，不表示同时患病）'] == detection['candidates']
        assert facts['样本备注（仅供参考）'] == '叶背发现小孔'
        assert '虫害线索' in prompt and '现在可以做什么' in prompt and '复拍与复检建议' in prompt
        assert '健康分类也不能排除虫害' in prompt
        image_url = parts[1]['image_url']['url']
        assert image_url.startswith('data:image/jpeg;base64,')
        with Image.open(io.BytesIO(base64.b64decode(image_url.split(',', 1)[1]))) as image:
            assert image.format == 'JPEG' and image.size == (32, 32)

        detail = response.json()
        assert detail['conversation']['title'] == f'{crop} · 叶片检测解读'
        summary, answer = detail['messages']
        assert summary['role'] == 'user' and answer['role'] == 'assistant'
        for expected in (f'作物：{crop}', f'分类结果：{label}', f'置信度：{score}', '处理与复检建议'):
            assert expected in summary['content']
        assert answer['content'] == '记下叶片变化与采样日期。'
        chat = client.get(f"/api/assistant/conversations/{detail['conversation']['id']}", headers=headers)
        assert chat.status_code == 200 and chat.json() == detail
        assert client.get(f"/api/detections/{detection['id']}").json() == detection
        assert client.post(route, headers=headers).json() == detail
        assert len(calls) == 1

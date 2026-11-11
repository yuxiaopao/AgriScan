"""Small, non-persistent checks for an administrator's draft LLM connection."""
import base64
import io
from ipaddress import ip_address
import json
from secrets import choice
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

import anyio
from fastapi import HTTPException
import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

MAX_PROBE_SECONDS = 25
MAX_REPLY_BYTES = 65536


def normalized_base(value):
    """Reject credentials and URL decorations before a secret can be sent."""
    try:
        if not value or any(ord(character) <= 32 for character in value):
            raise ValueError
        endpoint = urlsplit(value)
        host = endpoint.hostname or ''
        port = endpoint.port
        loopback = host.lower() == 'localhost'
        try:
            loopback = loopback or ip_address(host).is_loopback
        except ValueError:
            pass
        if (not host or endpoint.scheme not in {'https', 'http'}
                or (endpoint.scheme == 'http' and not loopback)
                or endpoint.username is not None or endpoint.password is not None
                or endpoint.query or endpoint.fragment or '\\' in value):
            raise ValueError
        host = host.encode('idna').decode('ascii').lower()
        authority = '[' + host + ']' if ':' in host else host
        if port is not None and port != {'https': 443, 'http': 80}[endpoint.scheme]:
            authority += ':' + str(port)
        return urlunsplit((endpoint.scheme, authority, endpoint.path.rstrip('/'), '', ''))
    except (ValueError, UnicodeError):
        raise ValueError('API 地址必须为 HTTPS 基础地址（本机回环可用 HTTP），不能包含账户、查询参数或片段。') from None


class LLMTestBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    llm_base_url: str = Field(min_length=1, max_length=2000)
    llm_model: str = Field(min_length=1, max_length=200)
    llm_timeout: int = Field(default=30, ge=1, le=120, strict=True)
    llm_api_key: SecretStr | None = Field(default=None, max_length=4096)

    @field_validator('llm_base_url')
    @classmethod
    def valid_base(cls, value):
        return normalized_base(value)

    @field_validator('llm_model')
    @classmethod
    def valid_model(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError('请填写有效模型名称。')
        return value

    @field_validator('llm_api_key')
    @classmethod
    def valid_key(cls, value):
        if value is not None:
            raw = value.get_secret_value()
            if not raw.strip() or any(ord(character) < 33 or ord(character) > 126 for character in raw):
                raise ValueError('请填写有效 API 密钥，保留已存密钥时省略此字段。')
        return value


def _failure(status, image):
    if status in {401, 403}:
        return '服务商未接受 API 密钥或当前账户权限，请检查凭据与模型授权。'
    if status == 402:
        return '服务商账户余额或额度不足，请补充额度后重试。'
    if status == 429:
        return '服务商当前限流或额度受限，请稍后重试。'
    if status == 404:
        return '未找到接口或模型，请检查 API 基础地址及模型名称。'
    if status in {400, 422}:
        return ('服务商未接受图片请求，请确认该模型支持 image_url 图片输入。' if image
                else '服务商未接受测试请求，请检查模型及 Chat Completions 兼容性。')
    if 300 <= status < 400:
        return '接口返回了重定向；为保护密钥，测试不会跟随跳转。'
    return '服务商暂时不可用，请稍后重试或检查接口配置。'


async def _completion(body, key, messages, image=False):
    # The request format matches the actual Xiaohe assistant. The short prompts
    # use no business records, uploads or personal data.
    cap = min(body.llm_timeout, 20)
    try:
        # Unlike a per-read timeout, this deadline also stops a peer that keeps
        # delivering tiny chunks forever. Both probes together take <=50s.
        with anyio.fail_after(min(body.llm_timeout, MAX_PROBE_SECONDS)):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(cap, connect=min(cap, 5), write=min(cap, 5), pool=min(cap, 5)),
                trust_env=False, follow_redirects=False, verify=True,
            ) as client:
                async with client.stream('POST', body.llm_base_url + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + key},
                    json={'model': body.llm_model, 'messages': [
                        {'role': 'system', 'content': 'Follow the test instructions. Reply briefly without explanation.'},
                        {'role': 'user', 'content': messages}], 'max_tokens': 128},
                ) as response:
                    if response.status_code != 200:
                        return None, _failure(response.status_code, image)
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(payload) + len(chunk) > MAX_REPLY_BYTES:
                            raise ValueError
                        payload.extend(chunk)
            content = json.loads(payload)['choices'][0]['message']['content']
        if not isinstance(content, str) or not content.strip() or len(content) > 4096:
            raise ValueError
        return content, None
    except (TimeoutError, httpx.TimeoutException):
        return None, '连接测试超时，请稍后重试或检查服务商响应速度。'
    except (httpx.HTTPError, OSError):
        return None, '无法建立可信连接，请检查 API 地址、网络和 HTTPS 证书。'
    except (ValueError, TypeError, KeyError, IndexError):
        return None, '未收到有效文本答复，请确认模型支持 Chat Completions 并关闭过长的推理输出。'


async def test_llm_connection(body, settings):
    started = monotonic()
    if 'llm_api_key' in body.model_fields_set:
        key = body.llm_api_key.get_secret_value() if body.llm_api_key is not None else ''
    else:
        try:
            same_target = normalized_base(settings.llm_base_url) == body.llm_base_url
        except ValueError:
            same_target = False
        if not same_target:
            raise HTTPException(422, 'API 地址已更改；请提供新密钥进行测试，不会把已存密钥发送到其他地址。')
        key = settings.llm_api_key
    if not key:
        raise HTTPException(422, '请先填写 API 密钥，或保留当前已保存的密钥。')
    if not isinstance(key, str) or any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise HTTPException(422, '已存 API 密钥格式无效，请重新填写后测试。')

    content, error = await _completion(body, key, 'Return only AGRISCAN_OK.')
    text_ok = content is not None and content.strip(' \n\t`\"\'.') == 'AGRISCAN_OK'
    text = {'ok': text_ok, 'message': '文本测试通过。' if text_ok else (error or '服务已有回复，但未通过简短文本指令测试。')}
    vision = {'ok': False, 'message': '文本测试未通过，尚未发送图片测试。'}
    if text_ok:
        color, rgb = choice([('red', (230, 20, 20)), ('green', (20, 180, 20)),
                             ('blue', (20, 20, 230)), ('yellow', (240, 220, 20))])
        data = io.BytesIO()
        Image.new('RGB', (128, 128), rgb).save(data, format='PNG')
        content, error = await _completion(body, key, [
            {'type': 'text', 'text': 'What color is this image? Return only one word: red, green, blue, or yellow. If you cannot see the image, return unknown.'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode('ascii')}},
        ], image=True)
        image_ok = content is not None and content.lower().strip(' \n\t`\"\'.') == color
        vision = {'ok': image_ok, 'message': '图片测试通过，模型正确识别了测试图颜色。' if image_ok
                  else (error or '接口返回了答复，但未正确识别测试图颜色，图片能力尚未验证。')}
    return {'ok': text['ok'] and vision['ok'], 'model': body.llm_model,
            'text': text, 'vision': vision, 'elapsed_ms': round((monotonic() - started) * 1000),
            'configuration_saved': False}

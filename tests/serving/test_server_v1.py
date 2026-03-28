import os

os.environ['BUTLER_API_KEYS'] = 'test-api-key-butler'
os.environ['BUTLER_API_KEY_REQUIRED'] = 'true'

from fastapi.testclient import TestClient

from scripts.serving.butler_server_v1 import create_app
from scripts.serving.server_config_v1 import load_config


VALID_KEY = 'test-api-key-butler'
AUTH = {'Authorization': f'Bearer {VALID_KEY}'}
client = TestClient(create_app(load_config()))


def test_healthz():
    res = client.get('/healthz')
    assert res.status_code == 200
    assert res.json()['status'] == 'ok'


def test_readyz_stub():
    res = client.get('/health/readyz')
    assert res.status_code == 200
    assert res.json()['status'] in ('stub', 'ready')


def test_list_models():
    res = client.get('/v1/models', headers=AUTH)
    assert res.status_code == 200
    data = res.json()
    assert data['object'] == 'list'
    ids = [item['id'] for item in data['data']]
    assert 'butler-small' in ids
    assert 'butler-micro' in ids
    assert 'butler-v1' in ids


def test_chat_completions_stub():
    res = client.post('/v1/chat/completions', headers=AUTH, json={
        'model': 'butler-small',
        'messages': [{'role': 'user', 'content': '안녕하세요'}],
    })
    assert res.status_code == 200
    body = res.json()
    assert body['choices'][0]['message']['role'] == 'assistant'
    assert body['usage']['total_tokens'] == -1


def test_chat_completions_stream_stub():
    with client.stream('POST', '/v1/chat/completions', headers=AUTH, json={
        'model': 'butler-small',
        'messages': [{'role': 'user', 'content': '테스트'}],
        'stream': True,
    }) as res:
        assert res.status_code == 200
        content = b''.join(res.iter_bytes()).decode('utf-8')
        assert 'data: [DONE]' in content
        assert 'chat.completion.chunk' in content


def test_invalid_model_404():
    res = client.post('/v1/chat/completions', headers=AUTH, json={
        'model': 'gpt-4',
        'messages': [{'role': 'user', 'content': '테스트'}],
    })
    assert res.status_code == 404


def test_auth_required_401():
    res = client.post('/v1/chat/completions', json={
        'model': 'butler-small',
        'messages': [{'role': 'user', 'content': '테스트'}],
    })
    assert res.status_code == 401


def test_invalid_api_key_403():
    res = client.post('/v1/chat/completions', headers={'Authorization': 'Bearer wrong-key'}, json={
        'model': 'butler-small',
        'messages': [{'role': 'user', 'content': '테스트'}],
    })
    assert res.status_code == 403


def test_openai_response_schema():
    res = client.post('/v1/chat/completions', headers=AUTH, json={
        'model': 'butler-micro',
        'messages': [{'role': 'user', 'content': '테스트'}],
    })
    body = res.json()
    for field in ['id', 'object', 'created', 'model', 'choices', 'usage']:
        assert field in body, f'{field} 누락'
    assert body['choices'][0]['finish_reason'] == 'stop'
    print('BUTLER_SERVER_SCHEMA' + '_OK=1')


def test_request_validation_422():
    res = client.post('/v1/chat/completions', headers=AUTH, json={
        'model': 'butler-small',
        'messages': [],
    })
    assert res.status_code == 422


def test_x_request_id_in_response():
    res = client.post('/v1/chat/completions', headers=AUTH, json={
        'model': 'butler-small',
        'messages': [{'role': 'user', 'content': '테스트'}],
    })
    assert 'x-request-id' in res.headers
    print('BUTLER_REQUEST_ID' + '_OK=1')


def test_metrics_endpoint():
    res = client.get('/metrics')
    assert res.status_code == 200
    body = res.json()
    assert 'requests_total' in body
    assert 'turboq_enabled' in body

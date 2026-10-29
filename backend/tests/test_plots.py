import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import inspect

from app.config import Settings
from app.db import Base, PlotDetails, make_database
from app.main import create_app
from fastapi.testclient import TestClient
from test_api import client, owned_demo_auth as auth, picture
from test_extensions import member_auth


def test_plot_coordinates_persist_update_and_clear(client):
    headers = auth(client)
    created = client.post('/api/plots', headers=headers, json={
        'name': '定位试验田', 'crop': '番茄', 'area': 2,
        'latitude': 26.572145, 'longitude': 106.713841,
    })
    assert created.status_code == 201
    plot = created.json()
    assert plot['latitude'] == 26.572145 and plot['cover_url'] is None
    url = f"/api/plots/{plot['id']}"
    assert client.patch(url, headers=headers, json={'name': '改名试验田'}).json()['longitude'] == 106.713841
    changed = client.patch(url, headers=headers, json={'latitude': 0, 'longitude': 0})
    assert changed.json()['latitude'] == 0 and changed.json()['longitude'] == 0
    cleared = client.patch(url, headers=headers, json={'latitude': None, 'longitude': None})
    assert cleared.json()['latitude'] is None and cleared.json()['longitude'] is None


@pytest.mark.parametrize('coordinates', [
    {'latitude': 91, 'longitude': 106}, {'latitude': 26, 'longitude': 181},
    {'latitude': 26}, {'longitude': 106}, {'latitude': None, 'longitude': 106},
    {'latitude': 'NaN', 'longitude': 106}, {'latitude': 26, 'longitude': 'Infinity'},
])
def test_invalid_coordinates_do_not_change_plot(client, coordinates):
    headers = auth(client)
    assert client.post('/api/plots', headers=headers, json={
        'name': 'invalid', 'crop': '番茄', 'area': 1, **coordinates,
    }).status_code == 422
    assert client.patch('/api/plots/plot-tomato', headers=headers, json=coordinates).status_code == 422
    assert client.get('/api/plots', headers=auth(client)).json()[0]['latitude'] is None


def test_cover_upload_replace_delete_preserves_coordinates_and_history(client):
    headers = auth(client)
    url = '/api/plots/plot-tomato'
    assert client.patch(url, headers=headers, json={'latitude': 26.57, 'longitude': 106.71}).status_code == 200
    data = io.BytesIO()
    Image.new('RGB', (2400, 1200), '#759965').save(data, format='PNG')
    uploaded = client.post(url + '/cover', headers=headers, files={'file': ('../../cover.png', data.getvalue(), 'image/png')})
    assert uploaded.status_code == 200
    cover = uploaded.json()['cover_url']
    assert uploaded.json()['latitude'] == 26.57
    stored = client.get(cover, headers=auth(client))
    assert stored.headers['content-type'] == 'image/jpeg'
    assert stored.headers['x-content-type-options'] == 'nosniff'
    assert Image.open(io.BytesIO(stored.content)).size == (1600, 800)
    assert next(row for row in client.get('/api/plots', headers=auth(client)).json() if row['id'] == 'plot-tomato')['cover_url'] == cover
    replaced = client.post(url + '/cover', headers=headers, files={'file': ('new.png', picture(), 'image/png')})
    new_cover = replaced.json()['cover_url']
    assert new_cover != cover and client.get(cover, headers=auth(client)).status_code == 404
    assert len(list(client.app.state.settings.upload_dir.iterdir())) == 1
    assert client.delete(url, headers=headers).status_code == 200
    assert client.get(new_cover, headers=auth(client)).status_code == 404
    assert client.get('/api/detections/demo-001', headers=auth(client)).json()['plot_id'] is None
    with client.app.state.session() as db:
        assert db.get(PlotDetails, 'plot-tomato') is None


@pytest.mark.parametrize('data,expected', [(b'not an image', 422), (b'x' * (10 * 1024 * 1024 + 1), 413)], ids=['corrupt', 'oversized'])
def test_invalid_cover_preserves_previous_image(client, data, expected):
    headers = auth(client)
    url = '/api/plots/plot-tomato/cover'
    original = client.post(url, headers=headers, files={'file': ('cover.png', picture(), 'image/png')}).json()['cover_url']
    assert client.post(url, headers=headers, files={'file': ('bad.png', data, 'image/png')}).status_code == expected
    assert client.get(original, headers=auth(client)).status_code == 200
    assert len(list(client.app.state.settings.upload_dir.iterdir())) == 1


def test_cover_permissions_and_missing_plot(client):
    payload = {'file': ('cover.png', picture(), 'image/png')}
    assert client.post('/api/plots/plot-tomato/cover', files=payload).status_code == 401
    assert client.post('/api/plots/plot-tomato/cover', headers=member_auth(client), files=payload).status_code == 404
    assert client.post('/api/plots/missing/cover', headers=auth(client), files=payload).status_code == 404
    assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_delete_cover_preserves_plot_coordinates_and_detection_history(client):
    headers = auth(client)
    url = '/api/plots/plot-tomato'
    client.patch(url, headers=headers, json={'latitude': 26.57, 'longitude': 106.71})
    uploaded = client.post(url + '/cover', headers=headers,
                           files={'file': ('cover.png', picture(), 'image/png')}).json()
    history = client.get('/api/detections/demo-001', headers=auth(client)).json()

    removed = client.delete(url + '/cover', headers=headers)
    assert removed.status_code == 200
    saved = removed.json()
    assert saved == {**uploaded, 'cover_url': None}
    assert client.get(uploaded['cover_url'], headers=auth(client)).status_code == 404
    assert list(client.app.state.settings.upload_dir.iterdir()) == []
    assert client.get('/api/detections/demo-001', headers=auth(client)).json() == history
    assert client.delete(url + '/cover', headers=headers).json() == saved


def test_delete_cover_without_details_is_idempotent_and_requires_ownership(client):
    url = '/api/plots/plot-tomato/cover'
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers=member_auth(client)).status_code == 404
    headers = auth(client)
    assert client.delete('/api/plots/missing/cover', headers=headers).status_code == 404
    before = next(row for row in client.get('/api/plots', headers=auth(client)).json() if row['id'] == 'plot-tomato')
    for _ in range(2):
        response = client.delete(url, headers=headers)
        assert response.status_code == 200 and response.json() == before
    with client.app.state.session() as db:
        assert db.get(PlotDetails, 'plot-tomato') is None


@pytest.mark.parametrize('action', ['replace-cover', 'delete-cover', 'delete-plot'])
def test_committed_plot_changes_succeed_when_old_cover_is_in_use(client, monkeypatch, caplog, action):
    headers = auth(client)
    url = '/api/plots/plot-tomato'
    client.patch(url, headers=headers, json={'latitude': 26.57, 'longitude': 106.71})
    uploaded = client.post(url + '/cover', headers=headers,
                           files={'file': ('cover.png', picture(), 'image/png')}).json()
    old_path = client.app.state.settings.upload_dir / Path(uploaded['cover_url']).name
    unlink = Path.unlink

    def locked_unlink(path, *args, **kwargs):
        if path == old_path:
            raise PermissionError('Image is in use')
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', locked_unlink)
        if action == 'replace-cover':
            response = client.post(url + '/cover', headers=headers,
                                   files={'file': ('new.png', picture(), 'image/png')})
        else:
            response = client.delete(url + ('/cover' if action == 'delete-cover' else ''), headers=headers)

    assert response.status_code == 200
    assert old_path.is_file() and client.get(uploaded['cover_url'], headers=auth(client)).status_code == 404
    assert any(record.levelname == 'WARNING' and old_path.name in record.message for record in caplog.records)
    history = client.get('/api/detections/demo-001', headers=auth(client)).json()
    if action == 'delete-plot':
        assert history['plot_id'] is None
        assert not any(row['id'] == 'plot-tomato' for row in client.get('/api/plots', headers=auth(client)).json())
    else:
        saved = response.json()
        assert saved['latitude'] == 26.57 and saved['longitude'] == 106.71
        assert history['plot_id'] == 'plot-tomato'
        if action == 'replace-cover':
            assert saved['cover_url'] != uploaded['cover_url']
            assert client.get(saved['cover_url'], headers=auth(client)).status_code == 200
        else:
            assert saved['cover_url'] is None


def test_existing_schema_is_extended_without_altering_plot_columns(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'existing.db'}", upload_dir=tmp_path / 'uploads',
                        redis_url='', model_manifest='', llm_enabled=False, email_verification_enabled=False)
    engine, _ = make_database(settings.database_url)
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name != 'plot_details'])
    with engine.connect() as connection:
        before = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='plots'").scalar_one()
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/plots').status_code == 200
        assert 'plot_details' in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='plots'").scalar_one() == before
    engine.dispose()

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from catalog_service import load_catalog_json, replace_catalog
from models import Category, Product


def sample_catalog():
    return {
        'updated_at': '2026-10-15T14:00:00+03:00', 'source': 'Тестовый прайс', 'unit': 'т',
        'groups': [
            {'slug': 'armatura', 'name': 'Арматура', 'items': [
                {'sku': 'a10', 'name': 'Арматура А500С 10', 'price': 62500.50, 'stock': 'Сочи'},
                {'sku': 'a12', 'name': 'Арматура А500С 12', 'price': None, 'stock': 'Сочи'}]},
            {'slug': 'list', 'name': 'Лист', 'items': [
                {'sku': 'l4', 'name': 'Лист 4 мм', 'price': 70000, 'stock': 'Сочи'}]},
        ],
    }


def fill(engine, data=None):
    with Session(engine) as session:
        with session.begin():
            replace_catalog(session, data or sample_catalog())


def test_alembic_schema_created(state):
    engine, _ = state
    assert {'categories', 'products', 'catalog_info', 'alembic_version'} <= set(inspect(engine).get_table_names())
    columns = {c['name']: c for c in inspect(engine).get_columns('products')}
    assert columns['price']['nullable']  # US03-T03: необязательная цена


def test_server_render_and_404(state):
    engine, client = state
    fill(engine)
    r = client.get('/katalog/armatura')
    assert r.status_code == 200
    assert 'Арматура А500С 10' in r.text
    assert '62\u202f500,50 ₽' in r.text  # шаблон выводит округление
    assert 'Уточняйте у менеджера' in r.text
    assert 'Лист 4 мм' not in r.text  # фильтрация категорией на сервере
    assert '<a href="/katalog/list"' in r.text
    assert client.get('/katalog/ne-suschestvuet').status_code == 404


def test_catalog_search_on_server(state):
    engine, client = state
    fill(engine)
    r = client.get('/katalog?q=%D0%BB%D0%B8%D1%81%D1%82')
    assert r.status_code == 200 and 'Лист 4 мм' in r.text
    assert 'Арматура А500С 10' not in r.text
    assert 'Найдено' in r.text
    r = client.get('/katalog?q=%3Cscript%3E')
    assert '<script>' not in r.text and '&lt;script&gt;' in r.text


def test_price_edit_in_db_reflected_without_json(state):
    engine, client = state
    fill(engine)
    with Session(engine) as session:
        with session.begin():
            product = session.scalar(select(Product).where(Product.sku == 'a12'))
            product.price = Decimal('123456.00')
    r = client.get('/katalog/armatura')
    assert r.status_code == 200
    assert '123\u202f456 ₽' in r.text
    assert client.get('/api/catalog-data').json()['groups'][0]['items'][1]['price'] == 123456.0
    assert client.get('/prices.json').json()['groups'][0]['items'][1]['price'] == 123456.0


def test_bad_price_does_not_erase_old_catalog(state):
    engine, client = state
    fill(engine)
    bad = sample_catalog()
    bad['groups'][0]['items'][0]['price'] = 'WRONG'
    with Session(engine) as session:
        with pytest.raises(ValueError):
            with session.begin():
                replace_catalog(session, bad)
    assert len(client.get('/api/catalog-data').json()['groups']) == 2
    assert 'Арматура А500С 10' in client.get('/katalog/armatura').text


def test_initial_data_from_existing_company_price_list(state):
    engine, client = state
    data = load_catalog_json(Path(__file__).resolve().parents[2] / 'site' / 'prices.json')
    fill(engine, data)
    answer = client.get('/api/catalog-data').json()
    assert len(answer['groups']) == len(data['groups'])
    assert sum(len(g['items']) for g in answer['groups']) == sum(len(g['items']) for g in data['groups'])
    for g in data['groups']:
        assert client.get('/katalog/' + g['slug']).status_code == 200


def test_empty_db_has_explanatory_page(state):
    _, client = state
    r = client.get('/katalog')
    assert r.status_code == 200
    assert 'Каталог пока не загружен' in r.text

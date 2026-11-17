"""Обновление каталога из прайса единым SQL-транзакционным набором."""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from models import Category, Product, CatalogInfo


def replace_catalog(session: Session, data: dict) -> tuple[int, int]:
    """Заменить все категории/позиции, не коммитя (транзакция у вызывающего кода).

    Сначала проверяем ВСЁ содержимое, чтобы ошибочный прайс не затёр каталог.
    """
    groups = data.get('groups')
    if not isinstance(groups, list) or not groups:
        raise ValueError('В прайсе нет категорий')
    validated = []
    slugs = set()
    total = 0
    for g in groups:
        if not isinstance(g, dict) or not g.get('slug') or not g.get('name') or not isinstance(g.get('items'), list):
            raise ValueError('Неверная структура категории')
        slug = str(g['slug'])
        if slug in slugs or len(slug) > 100:
            raise ValueError('Повторяющийся или слишком длинный slug')
        slugs.add(slug)
        if not g['items']:
            raise ValueError('Пустая категория')
        items = []
        for it in g['items']:
            if not isinstance(it, dict) or not it.get('name'):
                raise ValueError('Неверная товарная позиция')
            price = it.get('price')
            if price is not None:
                try:
                    price = Decimal(str(price))
                except (InvalidOperation, ValueError, TypeError) as ex:
                    raise ValueError('Цена должна быть числом или null') from ex
                if not price.is_finite() or price <= 0 or price > Decimal('9999999999.99'):
                    raise ValueError('Некорректная цена')
            items.append((str(it.get('sku', ''))[:100], str(it['name']), str(it.get('stock', 'Сочи'))[:100], price))
            total += 1
        validated.append((slug, str(g['name'])[:255], items))
    if total < 1:
        raise ValueError('Прайс пуст')

    # Удаление старых позиций и категорий — в транзакции; вне commit откатимо.
    session.execute(delete(Product))
    session.execute(delete(Category))
    for order, (slug, name, items) in enumerate(validated):
        cat = Category(slug=slug, name=name, sort_order=order)
        cat.products = [Product(sku=sku, name=title, stock=stock, price=price,
                                unit=str(data.get('unit') or 'т')[:20], sort_order=i)
                        for i, (sku, title, stock, price) in enumerate(items)]
        session.add(cat)
    info = session.get(CatalogInfo, 1)
    if info is None:
        info = CatalogInfo(id=1, updated_at='', source='')
        session.add(info)
    info.updated_at = str(data.get('updated_at') or '')[:40]
    info.source = str(data.get('source') or 'неизвестен')[:255]
    session.flush()
    return len(validated), total


def load_catalog_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def list_categories(session: Session) -> list[Category]:
    return list(session.scalars(select(Category).order_by(Category.sort_order, Category.id)))


def get_catalog_info(session: Session) -> CatalogInfo | None:
    return session.get(CatalogInfo, 1)


def catalog_as_json(session: Session) -> dict:
    cats = session.scalars(select(Category).options(selectinload(Category.products))
                           .order_by(Category.sort_order, Category.id)).all()
    info = get_catalog_info(session)
    return {
        'updated_at': info.updated_at if info else '',
        'source': info.source if info else '',
        'currency': 'RUB',
        'unit': 'т',
        'groups': [
            {'slug': c.slug, 'name': c.name, 'items': [
                {'sku': p.sku, 'name': p.name, 'stock': p.stock,
                 'price': float(p.price) if p.price is not None else None}
                for p in c.products]}
            for c in cats],
    }

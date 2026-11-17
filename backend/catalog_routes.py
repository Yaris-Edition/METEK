"""Каталог Sprint 1 — серверный рендеринг из PostgreSQL через Jinja2."""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from db import get_db
from models import Category, Product
from catalog_service import list_categories, get_catalog_info, catalog_as_json

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))


def price_label(value):
    if value is None:
        return 'Уточняйте у менеджера'
    formatted = f'{value:,.2f}' if value % 1 else f'{value:,.0f}'
    return formatted.replace(',', '\u202f').replace('.', ',') + ' ₽'


templates.env.filters['rub'] = price_label

# CSP основной витрины повторяет существующий nginx CSP (у админки другой, строгий).
CATALOG_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "form-action 'self'; base-uri 'self'; frame-ancestors 'self'; object-src 'none'"
)


def page(request: Request, session: Session, selected: Category | None, query: str = ''):
    cats = list_categories(session)
    if query:
        # Unicode casefold позволяет одинаково искать «Лист»/«лист» в PG и тестовой SQLite.
        tokens = query.casefold().split()
        rows = session.execute(
            select(Product, Category).join(Category).where(
                and_(*(Product.name_search.contains(t, autoescape=True) for t in tokens))
            ).order_by(Category.sort_order, Product.sort_order, Product.id)
        ).all()
    elif selected is not None:
        rows = session.execute(select(Product, Category).join(Category)
                               .where(Product.category_id == selected.id)
                               .order_by(Product.sort_order, Product.id)).all()
    else:
        rows = []
    info = get_catalog_info(session)
    return templates.TemplateResponse(request, 'catalog.html', {
        'categories': cats, 'selected': selected, 'rows': rows,
        'query': query, 'catalog_info': info,
    }, headers={'Content-Security-Policy': CATALOG_CSP, 'Cache-Control': 'no-store'})


@router.get('/katalog', include_in_schema=False)
def catalog_main(request: Request, q: str = Query('', max_length=80), db: Session = Depends(get_db)):
    cats = list_categories(db)
    return page(request, db, cats[0] if cats else None, q.strip())


@router.get('/katalog/{slug}', include_in_schema=False)
def catalog_category(request: Request, slug: str, db: Session = Depends(get_db)):
    category = db.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        raise HTTPException(status_code=404, detail='Категория не найдена')
    return page(request, db, category)


@router.get('/api/catalog-data', include_in_schema=False)
def catalog_data(db: Session = Depends(get_db)):
    """Для подсказок поиска на остальных страницах; данные только из БД."""
    return catalog_as_json(db)


@router.get('/prices.json', include_in_schema=False)
def legacy_catalog_data(db: Session = Depends(get_db)):
    """Обратная совместимость: прежний URL теперь тоже читает живую БД."""
    return catalog_as_json(db)

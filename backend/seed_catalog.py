"""Первоначальная загрузка существующего demo-прайса в PostgreSQL.

  cd backend
  python seed_catalog.py                  # только в пустую БД
  python seed_catalog.py --replace        # осознанно перезаписать каталог
"""
import argparse
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from db import get_engine
from models import Category
from catalog_service import load_catalog_json, replace_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description='Загрузка demo-data каталога Sprint 1')
    parser.add_argument('--file', type=Path, default=Path(__file__).parent.parent / 'site' / 'prices.json')
    parser.add_argument('--replace', action='store_true', help='Удалить старые категории и заменить их')
    args = parser.parse_args()
    with Session(get_engine()) as session:
        if session.scalar(select(Category.id).limit(1)) is not None and not args.replace:
            parser.error('Каталог уже заполнен — используйте --replace только при необходимости')
        data = load_catalog_json(args.file)
        with session.begin_nested():
            groups, products = replace_catalog(session, data)
        session.commit()
    print(f'Загружено из {args.file}: {groups} категорий, {products} позиций')


if __name__ == '__main__':
    main()

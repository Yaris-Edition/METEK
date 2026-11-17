"""Минимальные модели Sprint 1: виды проката и позиции с необязательной ценой."""
from decimal import Decimal
from sqlalchemy import ForeignKey, Integer, MetaData, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

NAMING = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products: Mapped[list['Product']] = relationship(
        back_populates='category', cascade='all, delete-orphan',
        order_by='Product.sort_order',
    )


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id', ondelete='CASCADE'), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_search: Mapped[str] = mapped_column(Text, nullable=False)
    stock: Mapped[str] = mapped_column(String(100), nullable=False, default='Сочи')
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default='т')
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[Category] = relationship(back_populates='products')

    @validates('name')
    def normalize_search(self, key, value):
        self.name_search = value.casefold()
        return value


class CatalogInfo(Base):
    """Дата и источник последнего опубликованного прайса; не история заказов."""
    __tablename__ = 'catalog_info'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)

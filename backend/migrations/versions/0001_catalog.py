"""Sprint 1: categories, products, catalog_info

Revision ID: 0001_catalog
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_catalog'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.UniqueConstraint('slug', name='uq_categories_slug'))
    op.create_index('ix_categories_slug', 'categories', ['slug'])
    op.create_table('products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('name_search', sa.Text(), nullable=False),
        sa.Column('stock', sa.String(length=100), nullable=False),
        sa.Column('price', sa.Numeric(12, 2), nullable=True),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name='fk_products_category_id_categories', ondelete='CASCADE'))
    op.create_index('ix_products_category_id', 'products', ['category_id'])
    op.create_table('catalog_info',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('updated_at', sa.String(length=40), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False))


def downgrade():
    op.drop_table('catalog_info')
    op.drop_index('ix_products_category_id', table_name='products')
    op.drop_table('products')
    op.drop_index('ix_categories_slug', table_name='categories')
    op.drop_table('categories')

"""elimina campos obsoletos de wishlist global en productos

Revision ID: 6f8d381e5b7e
Revises: 6ead33f62997
Create Date: 2026-09-01 20:05:54.953632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f8d381e5b7e'
down_revision: Union[str, Sequence[str], None] = '6ead33f62997'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('productos') as batch_op:
        batch_op.drop_column('en_wishlist')
        batch_op.drop_column('precio_al_agregar_wishlist')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('productos') as batch_op:
        batch_op.add_column(sa.Column('en_wishlist', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('precio_al_agregar_wishlist', sa.Float(), nullable=True))

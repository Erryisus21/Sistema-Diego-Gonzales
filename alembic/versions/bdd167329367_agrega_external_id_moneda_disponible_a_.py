"""agrega external_id moneda disponible a productos

Revision ID: bdd167329367
Revises: 6f8d381e5b7e
Create Date: 2026-09-02 18:33:34.184278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdd167329367'
down_revision: Union[str, Sequence[str], None] = '6f8d381e5b7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('productos') as batch_op:
        batch_op.add_column(sa.Column('external_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('moneda', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('disponible', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('productos') as batch_op:
        batch_op.drop_column('disponible')
        batch_op.drop_column('moneda')
        batch_op.drop_column('external_id')

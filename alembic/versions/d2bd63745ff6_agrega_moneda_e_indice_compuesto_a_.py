"""agrega moneda e indice compuesto a historial_precios

Revision ID: d2bd63745ff6
Revises: bdd167329367
Create Date: 2026-09-02 18:45:32.698693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2bd63745ff6'
down_revision: Union[str, Sequence[str], None] = 'bdd167329367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('historial_precios') as batch_op:
        batch_op.add_column(sa.Column('moneda', sa.String(), nullable=True))
        batch_op.create_index(
            'ix_historial_precios_producto_fecha', ['producto_id', 'fecha'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('historial_precios') as batch_op:
        batch_op.drop_index('ix_historial_precios_producto_fecha')
        batch_op.drop_column('moneda')

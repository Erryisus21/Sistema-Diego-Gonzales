"""agrega usuario_id a push_tokens

Revision ID: 6ead33f62997
Revises: 28a979a24142
Create Date: 2026-09-01 15:07:34.492969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ead33f62997'
down_revision: Union[str, Sequence[str], None] = '28a979a24142'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('push_tokens') as batch_op:
        batch_op.add_column(sa.Column('usuario_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_push_tokens_usuario_id', ['usuario_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_push_tokens_usuario_id_usuarios',
            'usuarios',
            ['usuario_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_tokens') as batch_op:
        batch_op.drop_constraint('fk_push_tokens_usuario_id_usuarios', type_='foreignkey')
        batch_op.drop_index('ix_push_tokens_usuario_id')
        batch_op.drop_column('usuario_id')

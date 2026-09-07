"""agrega restriccion unica tienda external_id a productos

Revision ID: 165a9b602408
Revises: 088da38f4ee0
Create Date: 2026-09-07 15:21:57.331488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '165a9b602408'
down_revision: Union[str, Sequence[str], None] = '088da38f4ee0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch_alter_table es necesario para que sea portable: SQLite no
    # soporta ALTER TABLE ... ADD CONSTRAINT directamente (Alembic
    # reconstruye la tabla internamente en modo batch); en PostgreSQL usa
    # la ruta nativa ADD CONSTRAINT sin problema. external_id sigue siendo
    # nullable=True: NULL nunca colisiona consigo mismo en ninguno de los
    # dos motores, así que esto no afecta datos legacy sin external_id.
    with op.batch_alter_table("productos") as batch_op:
        batch_op.create_unique_constraint(
            "uq_productos_tienda_external_id", ["tienda", "external_id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("productos") as batch_op:
        batch_op.drop_constraint("uq_productos_tienda_external_id", type_="unique")

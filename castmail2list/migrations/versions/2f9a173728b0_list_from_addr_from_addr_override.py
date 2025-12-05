"""list: from_addr -> from_addr_override

Revision ID: 2f9a173728b0
Revises: df7526f9612b
Create Date: 2025-12-04 17:20:00.224690

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f9a173728b0'
down_revision = 'df7526f9612b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('list', schema=None) as batch_op:
        batch_op.alter_column('from_addr', new_column_name='from_addr_override')


    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('list', schema=None) as batch_op:
        batch_op.alter_column('from_addr_override', new_column_name='from_addr')

    # ### end Alembic commands ###

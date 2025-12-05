"""list: from_addr_override -> from_addr_custom_default, from_addr_setting -> from_addr_mode_default

Revision ID: 0df3b2586a2c
Revises: 7e6ba9b0ffe1
Create Date: 2025-12-05 13:09:07.333883

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0df3b2586a2c'
down_revision = '7e6ba9b0ffe1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('list', schema=None) as batch_op:
        batch_op.alter_column('from_addr_setting', new_column_name='from_addr_mode_default')
        batch_op.alter_column('from_addr_override', new_column_name='from_addr_custom_default')

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('list', schema=None) as batch_op:
        batch_op.alter_column('from_addr_mode_default', new_column_name='from_addr_setting')
        batch_op.alter_column('from_addr_custom_default', new_column_name='from_addr_override')

    # ### end Alembic commands ###

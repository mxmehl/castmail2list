"""message: change table name

Revision ID: 33ec882b4a75
Revises: 66a3243eacad
Create Date: 2025-12-02 15:13:31.498975

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '33ec882b4a75'
down_revision = '66a3243eacad'
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table('message', 'email_in')
    # ### end Alembic commands ###


def downgrade():
    op.rename_table('email_in', 'message')
    # ### end Alembic commands ###

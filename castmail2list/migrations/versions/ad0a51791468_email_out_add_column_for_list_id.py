"""email_out: add column for list_id

Revision ID: ad0a51791468
Revises: 4b9dee6df9e1
Create Date: 2025-12-02 17:12:01.085179

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ad0a51791468"
down_revision = "4b9dee6df9e1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("email_out", schema=None) as batch_op:
        batch_op.add_column(sa.Column("list_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_email_out_list_id_list",
            "list",
            ["list_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("email_out", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_email_out_list_id_list",
            type_="foreignkey",
        )
        batch_op.drop_column("list_id")

"""email_in, email_out: composite pk for email_in and email_out fk update

Revision ID: c4ad571fe783
Revises: fee7c71e2327
Create Date: 2025-12-19 15:00:17.005000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c4ad571fe783'
down_revision = 'fee7c71e2327'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Make list_id in email_out non-nullable (it will be part of compound FK)
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.alter_column('list_id', nullable=False)

    # Step 2: Drop old FK constraint on email_out to email_in
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.drop_constraint('fk_email_out_email_in_mid_email_in', type_='foreignkey')

    # Step 3: Modify email_in table - drop old unique constraint and PK, create new composite PK
    with op.batch_alter_table('email_in', schema=None) as batch_op:
        # Drop unique constraint on message_id
        batch_op.drop_constraint('uq_email_in_message_id', type_='unique')
        # Drop old primary key
        batch_op.drop_constraint('pk_email_in', type_='primary')
        # Create new composite primary key
        batch_op.create_primary_key('pk_email_in', ['message_id', 'list_id'])

    # Step 4: Create new compound FK on email_out to email_in
    # Note: The FK to list.id remains unchanged
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_email_out_email_in',
            'email_in',
            ['email_in_mid', 'list_id'],
            ['message_id', 'list_id']
        )


def downgrade():
    # Step 1: Drop compound FK from email_out to email_in
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.drop_constraint('fk_email_out_email_in', type_='foreignkey')

    # Step 2: Restore old email_in primary key structure
    with op.batch_alter_table('email_in', schema=None) as batch_op:
        # Drop composite primary key
        batch_op.drop_constraint('pk_email_in', type_='primary')
        # Recreate single-column primary key
        batch_op.create_primary_key('pk_email_in', ['message_id'])
        # Recreate unique constraint
        batch_op.create_unique_constraint('uq_email_in_message_id', ['message_id'])

    # Step 3: Restore old FK on email_out to email_in
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_email_out_email_in_mid_email_in',
            'email_in',
            ['email_in_mid'],
            ['message_id']
        )

    # Step 4: Make list_id nullable again in email_out
    with op.batch_alter_table('email_out', schema=None) as batch_op:
        batch_op.alter_column('list_id', nullable=True)

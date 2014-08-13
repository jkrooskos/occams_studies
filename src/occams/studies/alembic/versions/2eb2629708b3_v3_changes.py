"""V3 changes

Revision ID: 2eb2629708b3
Revises: 60f4ba5ba66
Create Date: 2014-05-19 13:06:58.677357

"""

# revision identifiers, used by Alembic.
revision = '2eb2629708b3'
down_revision = '60f4ba5ba66'

from alembic import op
import sqlalchemy as sa
from six import string_types

from alembic import context


UPGRADE_USER = 'bitcore@ucsd.edu'


def upgrade():
    remove_zid_oldid()
    cleanup_attribute()
    cleanup_reftype()
    cleanup_patient()
    fix_numeric_choice_names()
    case_insensitive_names()
    merge_integer_decimal()
    merge_attribute_section()
    overhaul_attribute()


def downgrade():
    pass


def cleanup_attribute():
    op.drop_column('attribute', 'checksum')
    op.drop_column('attribute_audit', 'checksum')
    op.alter_column('attribute', 'is_required', server_default=sa.sql.false())
    op.alter_column('attribute', 'is_collection', server_default=sa.sql.false())
    op.alter_column('attribute', 'is_private', server_default=sa.sql.false())


def cleanup_reftype():
    op.rename_table('reftype', 'reference_type')
    op.drop_constraint('uq_reftype_name', 'reference_type')
    op.create_unique_constraint('uq_reference_type_name', 'reference_type', ['name'])

    op.rename_table('patientreference', 'patient_reference')
    op.rename_table('patientreference_audit', 'patient_reference_audit')
    op.drop_constraint('fk_patientreference_patient_id', 'patient_reference')
    op.create_foreign_key(
        'fk_patient_reference_patient_id',
        'patient_reference',
        'patient',
        ['patient_id'],
        ['id'],
        ondelete='CASCADE')
    op.alter_column('patient_reference', 'reftype_id', new_column_name='reference_type_id')
    op.alter_column('patient_reference_audit', 'reftype_id', new_column_name='reference_type_id')
    op.drop_constraint('fk_patientreference_reftype_id', 'patient_reference')
    op.create_foreign_key(
        'fk_patient_reference_reference_type_id',
        'patient_reference',
        'reference_type',
        ['reference_type_id'],
        ['id'],
        ondelete='CASCADE')
    op.drop_index('ix_patientreference_patient_id', 'patient_reference')
    op.create_index('ix_patient_reference_patient_id', 'patient_reference', ['patient_id'])
    op.drop_index('ix_patientreference_reference_number', 'patient_reference')
    op.create_index('ix_patient_reference_reference_number', 'patient_reference', ['reference_number'])
    op.drop_constraint('uq_patientreference_reference', 'patient_reference')
    op.create_unique_constraint('uq_patient_reference_reference_number', 'patient_reference', ['patient_id', 'reference_type_id', 'reference_number'])


def cleanup_patient():
    op.alter_column('patient', 'our', new_column_name='pid')
    op.drop_constraint('uq_patient_our', 'patient')
    op.create_unique_constraint('uq_patient_pid', 'patient', ['pid'])

    # Move legacy_number to reference numbers, where it should have been in the first place
    if 'aeh' in op.get_bind().engine.url.database:
        legacy_name = u'aeh_num'
        legacy_title = u'AEH Number'
    else:
        legacy_name = u'legacy_number'
        legacy_title = u'Legacy Number'
    op.execute("""
        INSERT INTO reference_type (name, title, create_user_id, create_date, modify_user_id, modify_date)
        VALUES (
              {}
            , {}
            , (SELECT "user".id FROM "user" WHERE key = {user})
            , CURRENT_TIMESTAMP
            , (SELECT "user".id FROM "user" WHERE key = {user})
            , CURRENT_TIMESTAMP
            )
    """.format(op.inline_literal(legacy_name), op.inline_literal(legacy_title), user=op.inline_literal(UPGRADE_USER)))
    op.execute("""
        INSERT INTO patient_reference (patient_id, reference_type_id, reference_number, create_user_id, create_date, modify_user_id, modify_date, revision)
        SELECT patient.id
             , (SELECT "reference_type".id FROM reference_type WHERE "reference_type".name = {legacy_name})
             , legacy_number
             , (SELECT "user".id FROM "user" WHERE key = {user})
             , CURRENT_TIMESTAMP
             , (SELECT "user".id FROM "user" WHERE key = {user})
             , CURRENT_TIMESTAMP
             , 1
        FROM patient
        WHERE patient.legacy_number iS NOT NULL
    """.format(legacy_name=op.inline_literal(legacy_name), user=op.inline_literal(UPGRADE_USER)))
    op.drop_column('patient', 'legacy_number')


def alter_enum(name, new_values, cols, new_name=None):
    """
    Modification of ENUMs is not very well supported in PostgreSQL so we have
    to do a bit of hacking to get this to work properly: swap the old
    type with a newly-created type of the same name
    """

    new_name = new_name or name

    op.execute('ALTER TYPE "{0}" RENAME TO "{0}_old"'.format(name))

    sa.Enum(*new_values, name=new_name).create(op.get_bind(), checkfirst=False)

    if isinstance(cols, string_types):
        cols = [cols]

    for col in cols:
        table_name, col_name = col.split('.')

        op.execute("""
            ALTER TABLE {0}
            ALTER COLUMN "{1}" TYPE "{2}"
            USING "{1}"::text::"{2}"
            """.format(table_name, col_name, new_name))

    op.execute('DROP TYPE "{0}_old"'.format(name))


def remove_zid_oldid():
    for table in ['site', 'patient', 'partner',
                  'enrollment', 'visit', 'study', 'cycle']:
        op.drop_column(table, 'zid')
        op.drop_column(table + '_audit', 'zid')

    untrack = [
        'partner',
        'arm', 'cycle', 'enrollment', 'patientreference',
        'reftype', 'site', 'stratum', 'study', 'visit',
        'attribute', 'value_blob', 'category', 'choice',
        'value_datetime', 'value_decimal', 'entity', 'value_integer',
        'schema', 'value_string', 'value_text',
        'context',
        'aliquot', 'aliquotstate', 'aliquottype',
        'location', 'specialinstruction',
        'specimen', 'specimenstate', 'specimentype']

    db = context.get_x_argument(as_dictionary=True).get('db')
    if db and 'cctg' in db:
        untrack += ['patient_log', 'patient_log_nonresponse_type']

    for table in untrack:
        op.drop_column(table, 'old_db')
        op.drop_column(table, 'old_id')


def fix_numeric_choice_names():
    op.create_check_constraint(
        'ck_choice_numeric_name',
        'choice',
        sa.cast(sa.sql.column('name'), sa.Integer) != sa.null())


def case_insensitive_names():

    op.alter_column('schema', 'name', type_=sa.String(32))
    op.alter_column('attribute', 'name', type_=sa.String(20))
    op.alter_column('choice', 'name', type_=sa.String(8))

    op.drop_constraint('schema_name_key', 'schema')
    # PG only
    op.execute('CREATE UNIQUE INDEX uq_schema_version ON schema (LOWER(name), publish_date)')

    op.drop_constraint('uq_attribute_name', 'attribute')
    op.execute('CREATE UNIQUE INDEX uq_attribute_name ON attribute (schema_id, LOWER(name))')

    op.drop_constraint('uq_choice_name', 'choice')
    op.execute('CREATE UNIQUE INDEX uq_choice_name ON choice (attribute_id, LOWER(name))')


def merge_integer_decimal():

    op.execute("DELETE FROM attribute_audit WHERE type = 'boolean'");

    new_types = ['blob', 'choice', 'date', 'datetime', 'integer', 'decimal', 'number', 'string', 'text']
    alter_enum('attribute_type', new_types, ['attribute.type', 'attribute_audit.type'])

    for table_name in ['attribute', 'attribute_audit']:

        op.add_column(
            table_name,
            sa.Column('decimal_places', sa.Integer()))

        table = sa.sql.table(table_name,
                             sa.sql.column('type'),
                             sa.sql.column('decimal_places'))

        op.execute(
            table.update()
            .where(table.c.type == op.inline_literal('integer'))
            .values(
                type=op.inline_literal('number'),
                decimal_places=op.inline_literal('0')))

        op.execute(
            table.update()
            .where(table.c.type == op.inline_literal('decimal'))
            .values(
                type=op.inline_literal('number'),
                decimal_places=sa.sql.null()))

    new_types = ['blob', 'choice', 'date', 'datetime', 'number', 'string', 'text']
    alter_enum('attribute_type', new_types, ['attribute.type', 'attribute_audit.type'])

    op.rename_table('value_decimal', 'value_number')
    op.rename_table('value_decimal_audit', 'value_number_audit')

    number_table = sa.sql.table(
        'value_number',
        sa.sql.column('entity_id'),
        sa.sql.column('attribute_id'),
        sa.sql.column('value'),
        sa.sql.column('create_date'),
        sa.sql.column('create_user_id'),
        sa.sql.column('modify_date'),
        sa.sql.column('modify_user_id'),
        sa.sql.column('revision'))

    integer_table = sa.sql.table(
        'value_number',
        sa.sql.column('entity_id'),
        sa.sql.column('attribute_id'),
        sa.sql.column('value'),
        sa.sql.column('create_date'),
        sa.sql.column('create_user_id'),
        sa.sql.column('modify_date'),
        sa.sql.column('modify_user_id'),
        sa.sql.column('revision'))

    op.execute(
        number_table.insert().from_select(
            [c.name for c in integer_table.c],
            integer_table.select()))

    op.drop_table('value_integer')
    op.drop_table('value_integer_audit')


def merge_attribute_section():
    new_types = ['blob', 'choice', 'date', 'datetime', 'number', 'section', 'string', 'text']
    alter_enum('attribute_type', new_types, ['attribute.type', 'attribute_audit.type'])

    op.add_column('attribute', sa.Column('parent_attribute_id', sa.Integer()))
    op.add_column('attribute_audit', sa.Column('parent_attribute_id', sa.Integer()))

    op.create_foreign_key(
        'fk_parent_attribute_id',
        'attribute',
        'attribute',
        ['parent_attribute_id'],
        ['id'],
        ondelete='CASCADE')

    attribute_table = sa.sql.table(
        'attribute',
        sa.sql.column('schema_id'),
        sa.sql.column('parent_attribute_id'),
        sa.sql.column('name'),
        sa.sql.column('title'),
        sa.sql.column('description'),
        sa.sql.column('type'),
        sa.sql.column('create_date'),
        sa.sql.column('create_user_id'),
        sa.sql.column('modify_date'),
        sa.sql.column('modify_user_id'),
        sa.sql.column('order'),
        sa.sql.column('revision'))

    section_table = sa.sql.table(
        'section',
        sa.sql.column('schema_id'),
        sa.sql.column('name'),
        sa.sql.column('title'),
        sa.sql.column('description'),
        sa.sql.column('create_date'),
        sa.sql.column('create_user_id'),
        sa.sql.column('modify_date'),
        sa.sql.column('modify_user_id'),
        sa.sql.column('order'),
        sa.sql.column('revision'))

    op.execute(
        section_table
        .update()
        .values(
            name=op.inline_literal('s_') + section_table.c.name,
            order=op.inline_literal(1000) + section_table.c.order))

    section_query = sa.select([
        section_table.c.schema_id,
        section_table.c.name,
        section_table.c.title,
        section_table.c.description,
        op.inline_literal('section').label('type'),
        section_table.c.create_date,
        section_table.c.create_user_id,
        section_table.c.modify_date,
        section_table.c.modify_user_id,
        section_table.c.order,
        section_table.c.revision])

    op.execute(
        attribute_table
        .insert()
        .from_select([c.name for c in section_query.c], section_query))

    # USE SQL, it's faster...
    op.execute("""
        UPDATE  attribute
        SET     parent_attribute_id = (
            SELECT  parent_attribute.id
            FROM    attribute AS parent_attribute
            JOIN    section ON (section.schema_id, section.name) = (parent_attribute.schema_id, parent_attribute.name)
            JOIN    section_attribute ON section_attribute.section_id = section.id
            WHERE   attribute.id = section_attribute.attribute_id)
        """)

    op.drop_table('section_attribute')
    op.drop_table('section')
    op.drop_table('section_audit')


def overhaul_attribute():

    if op.get_bind().dialect.name == 'postgresql':
        has_size_type = op.get_bind().execute(
            "select exists (select 1 from pg_type "
            "where typname='attribute_widget')").scalar()
        if not has_size_type:
            op.execute("CREATE TYPE attribute_widget AS ENUM ('checkbox', 'email', 'radio', 'select', 'telephone')")

    for table_name in ['attribute', 'attribute_audit']:

        op.alter_column(table_name, 'validator', new_column_name='pattern')

        op.add_column(
            table_name,
            sa.Column(
                'is_system',
                sa.Boolean(),
                nullable=False,
                server_default=sa.sql.false()))

        op.add_column(
            table_name,
            sa.Column(
                'is_readonly',
                sa.Boolean(),
                nullable=False,
                server_default=sa.sql.false()))

        op.add_column(
            table_name,
            sa.Column(
                'is_shuffled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.sql.false()))

        op.add_column(
            table_name,
            sa.Column('widget', sa.Enum('checkbox', 'email', 'radio', 'select', 'telephone', name='attribute_widget')))

        op.add_column(table_name, sa.Column('constraint_logic', sa.Text()))
        op.add_column(table_name, sa.Column('skip_logic', sa.Text()))

    op.drop_constraint('uq_attribute_order', 'attribute')
    op.create_unique_constraint(
        'uq_attribute_order',
        'attribute',
        ['schema_id', 'order'],
        deferrable=True,
        initially='DEFERRED')

    op.create_check_constraint(
        'ck_number_decimal_places',
        'attribute',
        "CASE WHEN type != 'number' THEN decimal_places IS NULL END")

    op.create_check_constraint(
        'ck_type_widget',
        'attribute',
        """
        CASE
            WHEN widget IS NOT NULL THEN
                CASE type
                    WHEN 'string' THEN widget IN ('telephone', 'email')
                    WHEN 'choice' THEN
                        CASE
                            WHEN is_collection THEN widget IN ('select', 'checkbox')
                            ELSE widget IN ('select', 'radio')
                        END
                END
        END
        """)

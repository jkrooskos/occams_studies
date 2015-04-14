"""
Code Book utitlities
"""

HEADER = [
    'table',
    'form',
    'publish_date',
    'field',
    'title',
    'description',
    'is_required',
    'is_system',
    'is_collection',
    'is_private',
    'type',
    'choices',
    'order',
    ]


FILE_NAME = 'codebook.csv'


class types:
    """
    Enum of supported types
    """
    BOOLEAN = 'boolean'
    CHOICE = 'choice'
    STRING = 'string'
    TEXT = 'text'
    BLOB = 'blob'
    DATE = 'date'
    DATETIME = 'datetime'
    TIME = 'time'
    NUMERIC = 'numeric'


def row(field, table, type,
        choices=[],
        form=None,  publish_date=None,
        title=None, desc=None, order=None,
        is_system=False,
        is_required=False, is_collection=False, is_private=False):
    """
    Helper function to create an codebook entry
    """
    return dict(
        field=field,
        table=table,
        type=type,
        form=form,
        publish_date=publish_date,
        title=title,
        description=desc,
        is_system=is_system,
        is_required=is_required,
        is_collection=is_collection,
        is_private=is_private,
        choices=sorted(choices, key=lambda v: int(v[0])),
        order=order)
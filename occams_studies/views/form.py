from pyramid.httpexceptions import HTTPBadRequest, HTTPOk
from pyramid.session import check_csrf_token
from pyramid.view import view_config
import sqlalchemy as sa
from sqlalchemy import orm
import wtforms
from wtforms.ext.dateutil.fields import DateField

from occams.utils.forms import wtferrors, ModelField, Form
from occams_datastore import models as datastore
from occams_forms.renderers import \
    make_form, render_form, entity_data, \
    form2json, version2json

from .. import _, models


def list_json(context, request):
    db_session = request.db_session

    external = context.__parent__

    query = (
        db_session.query(datastore.Entity)
        .options(orm.joinedload('schema'), orm.joinedload('state'))
        .join(datastore.Schema)
        .join(datastore.Context)
        .filter_by(external=external.__tablename__, key=external.id)
        # Do not show PHI forms since there are dedicated tabs for them
        .filter(~datastore.Schema.id.in_(
            db_session.query(models.patient_schema_table.c.schema_id)
            .subquery()))
        .order_by(datastore.Schema.name, datastore.Entity.collect_date))

    def fake_traverse(entity):
        entity.__parent__ = context
        return entity

    return {
        'entities': [
            view_json(fake_traverse(entity), request)
            for entity in query
        ]
    }


def view_json(context, request):
    """
    Converts an entity to JSON
    """

    external = context.__parent__.__parent__

    if isinstance(external, models.Visit):
        url = request.route_path(
            'studies.visit_form',
            patient=external.patient.pid,
            visit=external.visit_date.isoformat(),
            form=context.id)
    elif isinstance(external, models.Patient):
        url = request.route_path(
            'studies.patient_form',
            patient=external.pid,
            form=context.id)
    else:
        url = None

    if not context.state:
        state_data = None
    else:
        state_data = {
            'id': context.state.id,
            'name': context.state.name,
            'title': context.state.title,
        }

    return {
        '__url__': url,
        'id': context.id,
        'schema': {
            'name': context.schema.name,
            'title': context.schema.title,
            'publish_date': context.schema.publish_date.isoformat()
        },
        'collect_date': context.collect_date.isoformat(),
        'not_done': context.not_done,
        'state': state_data
    }


@view_config(
    route_name='studies.patient_forms',
    permission='edit',
    xhr=True,
    request_param='vocabulary=available_schemata',
    renderer='json')
@view_config(
    route_name='studies.patient_form',
    permission='edit',
    xhr=True,
    request_param='vocabulary=available_schemata',
    renderer='json')
@view_config(
    route_name='studies.visit',
    permission='edit',
    xhr=True,
    request_param='vocabulary=available_schemata',
    renderer='json')
@view_config(
    route_name='studies.visit_form',
    permission='edit',
    xhr=True,
    request_param='vocabulary=available_schemata',
    renderer='json')
def available_schemata(context, request):
    """
    Returns a list of available schemata for the given context

    Criteria for available schemata:
        * Must be configured for a study (i.e NOT patient/enrollment forms)
        * Must NOT be retracted

    GET parameters:
        schema -- (optional) only shows results for specific schema name
                  (useful for searching for a schema's publish dates)
        term -- (optional) filters by schema title or publish date
        grouped -- (optional) groups all results by schema name

    """
    db_session = request.db_session

    class SearchForm(Form):
        term = wtforms.StringField()
        schema = wtforms.StringField()
        grouped = wtforms.BooleanField()

    form = SearchForm(request.GET)
    form.validate()

    query = (
        db_session.query(datastore.Schema)
        # only allow forms that are available to active studies
        .join(models.study_schema_table)
        .join(models.Study)
        .filter(datastore.Schema.retract_date == sa.null()))

    if form.schema.data:
        query = query.filter(datastore.Schema.name == form.schema.data)

    if form.term.data:
        wildcard = u'%' + form.term.data + u'%'
        query = query.filter(
            datastore.Schema.title.ilike(wildcard)
            | sa.cast(datastore.Schema.publish_date,
                      sa.Unicode).ilike(wildcard))

    query = (
        query.order_by(
            datastore.Schema.title,
            datastore.Schema.publish_date.asc())
        .limit(100))

    if form.grouped.data:
        schemata = form2json(query)
    else:
        schemata = [version2json(i) for i in query]

    return {
        '__query__': form.data,
        'schemata': schemata
    }


@view_config(
    route_name='studies.visit_form',
    xhr=True,
    permission='view',
    renderer='string')
@view_config(
    route_name='studies.patient_form',
    xhr=True,
    permission='view',
    renderer='string')
def markup_ajax(context, request):
    """
    Returns the HTML markup of a form.

    This usually happens when a user has requested a different version
    of the form that they are trying to enter.
    """
    db_session = request.db_session
    version = request.GET.get('version')
    if not version:
        raise HTTPBadRequest()
    if version == context.schema.publish_date.isoformat():
        data = entity_data(context)
        schema = context.schema
    else:
        schema = (
            db_session.query(datastore.Schema)
            .filter_by(name=context.schema.name, publish_date=version)
            .one())
        data = None
    Form = make_form(db_session, schema, show_metadata=False)
    form = Form(request.POST, data=data)
    return render_form(form)


@view_config(
    route_name='studies.visit_forms',
    xhr=True,
    permission='add',
    request_method='POST',
    renderer='json')
@view_config(
    route_name='studies.patient_forms',
    xhr=True,
    permission='add',
    request_method='POST',
    renderer='json')
def add_json(context, request):
    check_csrf_token(request)
    db_session = request.db_session

    def check_study_form(form, field):
        if isinstance(context.__parent__, models.Patient):
            query = (
                db_session.query(datastore.Schema)
                .join(models.study_schema_table)
                .join(models.Study)
                .filter(datastore.Schema.id == field.data.id))
            (exists,) = db_session.query(query.exists()).one()
            if not exists:
                raise wtforms.ValidationError(request.localizer.translate(
                    _(u'This form is not assosiated with a study')))
        elif isinstance(context.__parent__, models.Visit):
            query = (
                db_session.query(models.Visit)
                .filter(models.Visit.id == context.__parent__.id)
                .join(models.Visit.cycles)
                .join(models.Cycle.study)
                .filter(
                    models.Cycle.schemata.any(id=field.data.id)
                    | models.Study.schemata.any(id=field.data.id)))
            (exists,) = db_session.query(query.exists()).one()
            if not exists:
                raise wtforms.ValidationError(request.localizer.translate(
                    _('${schema} is not part of the studies for this visit'),
                    mapping={'schema': field.data.title}))

    class AddForm(Form):
        schema = ModelField(
            db_session=db_session,
            class_=datastore.Schema,
            validators=[
                wtforms.validators.InputRequired(),
                check_study_form])
        collect_date = DateField(
            validators=[wtforms.validators.InputRequired()])

    form = AddForm.from_json(request.json_body)

    if not form.validate():
        raise HTTPBadRequest(json={'errors': wtferrors(form)})

    default_state = (
        db_session.query(datastore.State)
        .filter_by(name='pending-entry')
        .one())

    entity = datastore.Entity(
        schema=form.schema.data,
        collect_date=form.collect_date.data,
        state=default_state)

    if isinstance(context.__parent__, models.Visit):
        context.__parent__.entities.add(entity)
        context.__parent__.patient.entities.add(entity)
        next = request.current_route_path(
            _route_name='studies.visit_form', form=entity.id)
    elif isinstance(context.__parent__, models.Patient):
        context.__parent__.entities.add(entity)
        next = request.current_route_path(
            _route_name='studies.patient_form', form=entity.id)

    db_session.flush()

    request.session.flash(
        _('Successfully added new ${form}',
            mapping={'form': entity.schema.title}),
        'success')

    return {'__next__': next}


@view_config(
    route_name='studies.visit_forms',
    xhr=True,
    permission='delete',
    request_method='DELETE',
    renderer='json')
@view_config(
    route_name='studies.patient_forms',
    xhr=True,
    permission='delete',
    request_method='DELETE',
    renderer='json')
def bulk_delete_json(context, request):
    """
    Deletes forms in bulk
    """
    check_csrf_token(request)
    db_session = request.db_session

    class DeleteForm(Form):
        forms = wtforms.FieldList(
            ModelField(
                db_session=db_session,
                class_=datastore.Entity),
            validators=[
                wtforms.validators.DataRequired()])

    form = DeleteForm.from_json(request.json_body)

    if not form.validate():
        raise HTTPBadRequest(json={'errors': wtferrors(form)})

    entity_ids = [entity.id for entity in form.forms.data]

    external = context.__parent__.__tablename__
    key = context.__parent__.id

    (db_session.query(datastore.Entity)
        .filter(datastore.Entity.id.in_(
            db_session.query(datastore.Context.entity_id)
            .filter(datastore.Context.entity_id.in_(entity_ids))
            .filter(datastore.Context.external == external)
            .filter(datastore.Context.key == key)))
        .delete('fetch'))

    db_session.flush()

    return HTTPOk()

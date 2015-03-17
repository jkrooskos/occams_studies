from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from pyramid.session import check_csrf_token
from pyramid.view import view_config
import six
from slugify import slugify
import wtforms

from occams.forms.utils import form2json

from .. import _, models, Session
from ..utils import wtferrors


@view_config(
    route_name='cycle',
    permission='view',
    xhr=True,
    renderer='json')
def view_json(context, request):
    cycle = context
    return {
        '__url__': request.route_path('cycle',
                                      study=cycle.study.name,
                                      cycle=cycle.name),
        'id': cycle.id,
        'name': cycle.name,
        'title': cycle.title,
        'week': cycle.week,
        'is_interim': cycle.is_interim,
        'forms': form2json(cycle.schemata)
        }


@view_config(
    route_name='cycles',
    permission='add',
    request_method='POST',
    xhr=True,
    renderer='json')
@view_config(
    route_name='cycle',
    permission='edit',
    request_method='PUT',
    xhr=True,
    renderer='json')
def edit_json(context, request):
    check_csrf_token(request)

    form = CycleSchema(context, request).from_json(request.json_body)

    if not form.validate():
        raise HTTPBadRequest(json={'errors': wtferrors(form)})

    if isinstance(context, models.CycleFactory):
        cycle = models.Cycle(study=context.__parent__)
        Session.add(cycle)
    else:
        cycle = context

    cycle.name = six.text_type(slugify(form.title.data))
    cycle.title = form.title.data
    cycle.week = form.week.data
    cycle.is_interim = form.is_interim.data

    Session.flush()

    return view_json(cycle, request)


@view_config(
    route_name='cycle',
    permission='delete',
    request_method='DELETE',
    xhr=True,
    renderer='json')
def delete_json(context, request):
    check_csrf_token(request)

    (has_visits,) = (
        Session.query(
            Session.query(models.Visit)
            .filter(models.Visit.cycles.any(id=context.id))
            .exists())
        .one())

    if has_visits and not request.has_permission('admin', context):
        raise HTTPForbidden(_(u'Cannot delete a cycle with visits'))

    Session.delete(context)
    Session.flush()

    return {
        '__next__': request.route_path('study', study=context.study.name),
        'message': _(u'Successfully removed "${cycle}"',
                     mapping={'cycle': context.title})
        }


def CycleSchema(context, request):

    def check_unique_url(form, field):
        slug = six.text_type(slugify(field.data))
        query = Session.query(models.Cycle).filter_by(name=slug)
        if isinstance(context, models.Cycle):
            query = query.filter(models.Cycle.id != context.id)
        (exists,) = Session.query(query.exists()).one()
        if exists:
            raise wtforms.ValidationError(request.localizer.translate(_(
                u'Does not yield a unique URL.')))

    class CycleForm(wtforms.Form):
        title = wtforms.StringField(
            validators=[
                wtforms.validators.InputRequired(),
                wtforms.validators.Length(min=3, max=32),
                check_unique_url])
        week = wtforms.IntegerField()
        is_interim = wtforms.BooleanField()

    return CycleForm

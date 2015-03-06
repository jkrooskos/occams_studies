from pyramid.httpexceptions import HTTPForbidden
from pyramid.view import forbidden_view_config


@forbidden_view_config(renderer='../templates/error/forbidden.pt')
def forbidden(request):
    """
    Error handler when a user has insufficient privilidges.

    Note that Pyramid combines unauthorized actions into the Forbidden HTTP
    exception, which means we have to check if the user is authenticated and
    does not have sufficient prilidges or is not logged in. If they user
    is not logged in we need to continue the Forbidden exception so it gets
    picked up by the single-sign-on mechanism (hopefully)
    """

    is_logged_in = bool(request.authenticated_userid)

    if not is_logged_in:
        return HTTPForbidden()

    return {}
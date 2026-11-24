from rest_framework.viewsets import GenericViewSet as OGGenericViewSet

from jadaun.views.view import LookupFieldMixin


class BaseAPIViewSet(OGGenericViewSet, LookupFieldMixin):
    """
    Base class for all API viewsets. This class is used to identify API
    viewsets in the application. All API viewsets should inherit from this class.
    """

    view_url: str | None = None

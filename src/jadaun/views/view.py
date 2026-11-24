from typing import NoReturn

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import APIView as OGAPIView


class LookupFieldMixin:
    """
    Lookup Field functionality for OGAPIView
    """

    lookup_field = "pk"  # (Database Side) represents the model field name.
    lookup_url_kwarg = (
        None  # (URL Side) represents the variable name used in urlpatterns.
    )
    model = None  # model the APIView belongs to.

    def get_object(self):
        assert self.model is not None, (
            f"{self.__class__.__qualname__} must include a `model` attribute."
        )
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        filter_kwargs = {
            self.lookup_field: getattr(self, "kwargs", {}).get(lookup_url_kwarg)
        }
        return get_object_or_404(klass=self.model, **filter_kwargs)


class ViewError(APIException):
    def __init__(self, detail: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(detail=detail)


class BaseAPIView(OGAPIView, LookupFieldMixin):
    """
    Base class for all API views. This class is used to identify API views
    in the application. All API views should inherit from this class.
    """

    view_url: str | None = None

    # Set by `APIViewRouter` through `as_view(**initkwargs)`; declared here
    # so Django's `View.as_view` accepts them as valid keyword arguments.
    basename: str | None = None
    detail: bool = False

    def fail(
        self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST
    ) -> NoReturn:
        """Abort the current request with `message` as the error detail.

        Raises a `ViewError`, which DRF's exception handler turns into a
        Response with `status_code` and `{"detail": message}` as the body.
        """
        raise ViewError(detail=message, status_code=status_code)

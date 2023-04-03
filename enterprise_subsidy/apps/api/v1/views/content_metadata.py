"""
Views for the enterprise-subsidy service relating to content metadata.
"""
import requests
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from edx_rbac.mixins import PermissionRequiredMixin
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_404_NOT_FOUND

from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.decorators import require_at_least_one_query_parameter
from enterprise_subsidy.apps.api_client.enterprise_catalog import EnterpriseCatalogApiClient
from enterprise_subsidy.apps.subsidy.constants import (
    EDX_PRODUCT_SOURCE,
    EDX_VERIFIED_COURSE_MODE,
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    EXECUTIVE_EDUCATION_MODE,
    PERMISSION_CAN_READ_CONTENT_METADATA
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment


class ContentMetadataViewSet(
    PermissionRequiredMixin,
    GenericAPIView
):
    """
    Subsidy service viewset partaining to content metadata.

    GET /api/v1/content-metadata/{Content Identifier}/

    Note: content identifier can be either content key or uuid

    Required query param:
        enterprise_customer_uuid (uuid): The UUID associated with the requesting user's enterprise customer
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    allowed_roles = [
        ENTERPRISE_SUBSIDY_ADMIN_ROLE,
        ENTERPRISE_SUBSIDY_LEARNER_ROLE,
        ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    ]
    role_assignment_class = EnterpriseSubsidyRoleAssignment

    permission_required = PERMISSION_CAN_READ_CONTENT_METADATA

    def get_permission_object(self):
        """
        Determine the correct enterprise customer uuid that role-based
        permissions should be checked against.
        """
        return str(self.requested_enterprise_customer_uuid)

    @property
    def requested_enterprise_customer_uuid(self):
        """
        Look in the query parameters for an enterprise customer UUID.
        """
        return utils.get_enterprise_uuid_from_request_query_params(self.request)

    @method_decorator(cache_page(60))
    @method_decorator(require_at_least_one_query_parameter('enterprise_customer_uuid'))
    @action(detail=True)
    def get(self, request, content_identifier, enterprise_customer_uuid):
        """
        GET entry point for the `ContentMetadataViewSet`

        Fetches subsidy related content metadata.

        Returns:
            Subsidy content metadata payload:
                content_uuid (uuid4): UUID identifier conencted to the content
                content_key (str): String content key identifier connected to the content
                source (str): Product source string, as of 3/16/23 this is either `2u` or `edX`.
                content_price (float): Float representation of the course price in USD cents,
                  read from either the ``first_enrollable_paid_seat_price`` or from ``entitlements``
                  for the content.

            404 Content Not Found IFF
                - The content identifier does not exist OR the content is not connected to the enterprise customer
                    via an enterprise catalog query
                - The content metadata payload does not contain an appropriate entitlement mode and price or the
                    content's associated product source
        """
        catalog_client = EnterpriseCatalogApiClient()
        try:
            content_data = catalog_client.get_content_metadata_for_customer(
                enterprise_customer_uuid[0],
                content_identifier
            )
            if source_dict := content_data.get('product_source'):
                content_source = source_dict.get('name')
                source_mode = EXECUTIVE_EDUCATION_MODE
            else:
                content_source = EDX_PRODUCT_SOURCE
                source_mode = EDX_VERIFIED_COURSE_MODE

            content_price = catalog_client.price_for_content(content_data, source_mode)

            if not content_price:
                return Response("Could not find course price in content data payload", 404)

            response_body = {
                'content_uuid': content_data.get('uuid'),
                'content_key': content_data.get('key'),
                'source': content_source,
                'content_price': content_price,
            }
        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code == 404:
                return Response("Content not found", HTTP_404_NOT_FOUND)
            return Response(f"Failed to fetch data from catalog service with exc: {exc}", exc.response.status_code)
        return Response(response_body, 200)

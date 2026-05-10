"""REST API views for annotation endpoints."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from opencontractserver.llms.tools.image_tools import (
    get_annotation_images_with_permission,
)

logger = logging.getLogger(__name__)


class AnnotationImagesThrottle(UserRateThrottle):
    """Rate limiting for annotation image retrieval endpoint (authenticated only).

    Bypasses anonymous requests so each user-type has a single dedicated
    bucket — anon traffic is metered exclusively by ``AnnotationImagesAnonThrottle``.
    Without this gate, ``UserRateThrottle`` would IP-key anonymous requests
    against ``annotation_images`` while ``AnonRateThrottle`` IP-keyed them
    against ``annotation_images_anon``, consuming two cache slots per call
    in lockstep.
    """

    scope = "annotation_images"

    def allow_request(self, request, view):
        if not request.user.is_authenticated:
            return True
        return super().allow_request(request, view)


class AnnotationImagesAnonThrottle(AnonRateThrottle):
    """Rate limiting for annotation image retrieval endpoint (anonymous only).

    Bypasses authenticated requests; the matching ``AnnotationImagesThrottle``
    handles those. See that class for the rationale behind splitting the
    two scopes.
    """

    scope = "annotation_images_anon"

    def allow_request(self, request, view):
        if request.user.is_authenticated:
            return True
        return super().allow_request(request, view)


class AnnotationImagesView(APIView):
    """
    REST endpoint to fetch image data for an annotation.

    GET /api/annotations/<annotation_id>/images/

    Returns JSON with base64-encoded images for the specified annotation.
    Uses get_annotation_images_with_permission() which mirrors the visibility
    rules of AnnotationQuerySet.visible_to_user:
    - Authenticated users: requires READ permission on document AND corpus,
      respects analysis/extract privacy fields
    - Anonymous users: only structural annotations on public document +
      public corpus (matches the public/anonymous read access defined in
      docs/permissioning/consolidated_permissioning_guide.md)
    - Returns empty array for unauthorized/missing (IDOR protection)

    Rate limited to 200 requests/hour per user/IP to prevent resource exhaustion.
    Authenticated and anonymous callers each have their own bucket so anon
    traffic cannot starve the authenticated quota and vice versa.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnnotationImagesThrottle, AnnotationImagesAnonThrottle]

    def get(self, request, annotation_id):
        """
        Fetch all images referenced by an annotation.

        Args:
            request: Django request object
            annotation_id: ID of the annotation

        Returns:
            JSON response with images array containing base64 data
        """
        try:
            images = get_annotation_images_with_permission(
                user=request.user, annotation_id=annotation_id
            )

            # Convert ImageData Pydantic models to dicts for JSON serialization
            images_data = [
                {
                    "base64_data": img.base64_data,
                    "format": img.format,
                    "data_url": img.data_url,
                    "page_index": img.page_index,
                    "token_index": img.token_index,
                }
                for img in images
            ]

            return Response(
                {
                    "annotation_id": str(annotation_id),
                    "images": images_data,
                    "count": len(images_data),
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            # Log with full traceback for debugging, but don't expose details to client
            logger.exception(
                f"Unexpected error fetching annotation images for annotation_id={annotation_id}"
            )
            # Return empty array for any error (IDOR protection)
            # Same response for missing, unauthorized, or unexpected errors
            return Response(
                {"annotation_id": str(annotation_id), "images": [], "count": 0},
                status=status.HTTP_200_OK,
            )

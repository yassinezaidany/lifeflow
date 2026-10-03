from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Object-level guard. Querysets are already user-scoped; this is defence in depth."""

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user_id", None) == request.user.id


class OwnedQuerysetMixin:
    """Restrict every queryset to the requesting user and stamp ownership on create.

    Records that belong to another user are therefore invisible (404), never 403,
    which avoids leaking their existence.
    """

    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

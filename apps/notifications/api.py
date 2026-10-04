from django.conf import settings
from django.utils.translation import gettext as _
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.api.mixins import OwnedQuerysetMixin

from .models import Notification, PushSubscription
from .push import push_enabled, send_push


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "url", "is_read", "created_at"]
        read_only_fields = ["kind", "title", "body", "url", "created_at"]


class PushSubscriptionInput(serializers.Serializer):
    endpoint = serializers.URLField(max_length=600)
    keys = serializers.DictField(child=serializers.CharField(max_length=200))

    def validate_endpoint(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError(_("Invalid push endpoint."))
        return value

    def validate_keys(self, value):
        if not value.get("p256dh") or not value.get("auth"):
            raise serializers.ValidationError(_("Missing subscription keys."))
        return value


class NotificationViewSet(OwnedQuerysetMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})

    @action(detail=False, methods=["get"], url_path="push/key")
    def push_key(self, request):
        return Response({
            "enabled": push_enabled(),
            "public_key": settings.VAPID_PUBLIC_KEY if push_enabled() else None,
            "devices": PushSubscription.objects.filter(user=request.user).count(),
        })

    @action(detail=False, methods=["post"], url_path="push/subscribe")
    def push_subscribe(self, request):
        if not push_enabled():
            raise ValidationError({"detail": _("Push notifications are not configured on this server.")})
        data = PushSubscriptionInput(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        # An endpoint belongs to one browser: re-assign it if another account used this device before.
        sub = PushSubscription.objects.filter(endpoint_hash=PushSubscription.hash_endpoint(v["endpoint"])).first() or PushSubscription(endpoint=v["endpoint"])
        sub.user = request.user
        sub.p256dh, sub.auth = v["keys"]["p256dh"], v["keys"]["auth"]
        sub.user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
        sub.save()
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="push/unsubscribe")
    def push_unsubscribe(self, request):
        endpoint_hash = PushSubscription.hash_endpoint(str(request.data.get("endpoint", "")))
        deleted, _x = PushSubscription.objects.filter(user=request.user, endpoint_hash=endpoint_hash).delete()
        return Response({"unsubscribed": bool(deleted)})

    @action(detail=False, methods=["post"], url_path="push/test")
    def push_test(self, request):
        sent = send_push(request.user, _("LifeFlow notifications work 🎉"), _("You'll be reminded here."), "/today/", tag="test")
        return Response({"sent": sent})

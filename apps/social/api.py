"""Read-only social API (for a future mobile client). Writes go through the web views."""
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from . import services
from .models import Friendship, SharedChallenge


def _person(user):
    return {"id": user.pk, "username": user.username, "name": services.display_name(user), "initials": user.initials}


@api_view(["GET"])
def friends(request):
    user = request.user
    return Response({
        "friends": [_person(u) for u in services.friends_of(user)],
        "incoming": [{"id": f.pk, "from": _person(f.from_user)} for f in Friendship.objects.filter(to_user=user, status="pending").select_related("from_user")],
        "outgoing": [{"id": f.pk, "to": _person(f.to_user)} for f in Friendship.objects.filter(from_user=user, status="pending").select_related("to_user")],
    })


@api_view(["GET"])
def shared_list(request):
    return Response([
        {"id": s.pk, "name": s.name, "icon": s.icon, "color": s.color, "members": s.member_count,
         "start_date": s.start_date, "end_date": s.end_date}
        for s in services.shared_for_user(request.user)
    ])


@api_view(["GET"])
def shared_leaderboard(request, pk):
    shared = get_object_or_404(SharedChallenge, pk=pk)
    if not services.is_active_member(shared, request.user):
        raise NotFound
    return Response({"id": shared.pk, "name": shared.name, "rows": services.leaderboard(shared, request.user)})

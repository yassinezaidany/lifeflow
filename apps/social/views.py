from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.challenges.models import Challenge, ChallengeTemplate

from . import services
from .models import Friendship, SharedChallenge, SharedChallengeMember

User = get_user_model()


def _error(request, exc):
    if isinstance(exc, ValidationError):
        text = " ".join(m for msgs in getattr(exc, "message_dict", {"": exc.messages}).values() for m in msgs)
    else:
        text = str(exc)
    messages.error(request, text or _("This action is not allowed."))


@login_required
def community(request):
    user = request.user
    shared = list(services.shared_for_user(user))
    my_status = {m.shared_id: m.status for m in SharedChallengeMember.objects.filter(user=user, shared__in=shared)}
    return render(request, "social/community.html", {
        "friends": services.friends_of(user),
        "incoming": Friendship.objects.filter(to_user=user, status=Friendship.Status.PENDING).select_related("from_user"),
        "outgoing": Friendship.objects.filter(from_user=user, status=Friendship.Status.PENDING).select_related("to_user"),
        "shared_active": [s for s in shared if my_status.get(s.pk) == SharedChallengeMember.Status.ACTIVE],
        "shared_invites": [s for s in shared if my_status.get(s.pk) == SharedChallengeMember.Status.INVITED],
        "templates": services.community_templates()[:30],
        "my_templates": ChallengeTemplate.objects.filter(owner=user, is_public=True),
        "tab": request.GET.get("tab", "friends"),
    })


@login_required
@require_POST
def friend_add(request):
    try:
        f = services.send_friend_request(request.user, request.POST.get("username", ""))
        messages.success(request, _("You are now friends.") if f.status == Friendship.Status.ACCEPTED else _("Friend request sent."))
    except ValidationError as exc:
        _error(request, exc)
    return redirect("social:community")


@login_required
@require_POST
def friend_respond(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk, to_user=request.user, status=Friendship.Status.PENDING)
    accept = request.POST.get("action") == "accept"
    services.respond_to_request(friendship, request.user, accept)
    messages.success(request, _("Friend request accepted.") if accept else _("Friend request declined."))
    return redirect("social:community")


@login_required
@require_POST
def friend_cancel(request, pk):
    Friendship.objects.filter(pk=pk, from_user=request.user, status=Friendship.Status.PENDING).delete()
    return redirect("social:community")


@login_required
@require_POST
def friend_remove(request, user_id):
    other = get_object_or_404(User, pk=user_id)
    services.remove_friend(request.user, other)
    messages.success(request, _("Friend removed."))
    return redirect("social:community")


@login_required
@require_POST
def share_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, pk=challenge_id, user=request.user)
    shared = services.share_challenge(request.user, challenge)
    messages.success(request, _("Group challenge created — invite your friends."))
    return redirect("social:shared", pk=shared.pk)


def _shared_for(request, pk) -> tuple[SharedChallenge, SharedChallengeMember]:
    shared = get_object_or_404(SharedChallenge, pk=pk)
    member = services.membership(shared, request.user)
    if member is None or member.status == SharedChallengeMember.Status.LEFT:
        raise Http404  # non-members don't learn that the group exists
    return shared, member


@login_required
def shared_detail(request, pk):
    shared, member = _shared_for(request, pk)
    if member.status == SharedChallengeMember.Status.INVITED:
        return redirect("social:join", code=shared.invite_code)
    member_ids = set(shared.members.exclude(status=SharedChallengeMember.Status.LEFT).values_list("user_id", flat=True))
    return render(request, "social/shared_detail.html", {
        "shared": shared, "member": member, "rows": services.leaderboard(shared, request.user),
        "invitable": [f for f in services.friends_of(request.user) if f.pk not in member_ids],
        "pending": shared.members.filter(status=SharedChallengeMember.Status.INVITED).select_related("user"),
        "invite_url": request.build_absolute_uri(f"/community/join/{shared.invite_code}/"),
        "is_owner": shared.owner_id == request.user.pk,
    })


@login_required
@require_POST
def shared_invite(request, pk):
    shared, _member = _shared_for(request, pk)
    friend = get_object_or_404(User, pk=request.POST.get("user_id"))
    try:
        services.invite_friend(shared, request.user, friend)
        messages.success(request, _("Invitation sent to %(name)s.") % {"name": services.display_name(friend)})
    except (ValidationError, PermissionDenied) as exc:
        _error(request, exc)
    return redirect("social:shared", pk=pk)


@login_required
@require_POST
def shared_privacy(request, pk):
    _shared, member = _shared_for(request, pk)
    member.share_progress = not member.share_progress
    member.save(update_fields=["share_progress", "updated_at"])
    return redirect("social:shared", pk=pk)


@login_required
@require_POST
def shared_leave(request, pk):
    shared, _member = _shared_for(request, pk)
    try:
        services.leave_shared(shared, request.user)
        messages.success(request, _("You left the group. Your challenge and entries are still yours."))
    except ValidationError as exc:
        _error(request, exc)
        return redirect("social:shared", pk=pk)
    return redirect("social:community")


@login_required
@require_POST
def shared_close(request, pk):
    shared, _member = _shared_for(request, pk)
    try:
        services.close_shared(shared, request.user)
        messages.success(request, _("Group challenge closed. Everyone keeps their own challenge."))
    except PermissionDenied as exc:
        _error(request, exc)
        return redirect("social:shared", pk=pk)
    return redirect("social:community")


@login_required
def join(request, code):
    shared = get_object_or_404(SharedChallenge, invite_code=code, is_active=True)
    member = services.membership(shared, request.user)
    if member and member.status == SharedChallengeMember.Status.ACTIVE:
        return redirect("social:shared", pk=shared.pk)
    if request.method == "POST":
        if request.POST.get("action") == "decline":
            services.decline_invitation(shared, request.user)
            messages.info(request, _("Invitation declined."))
            return redirect("social:community")
        try:
            services.join_shared(shared, request.user)
            messages.success(request, _("Welcome to “%(name)s”! The challenge was added to your challenges.") % {"name": shared.name})
            return redirect("social:shared", pk=shared.pk)
        except ValidationError as exc:
            _error(request, exc)
    return render(request, "social/join.html", {
        "shared": shared, "owner_name": services.display_name(shared.owner),
        "member_count": shared.members.filter(status=SharedChallengeMember.Status.ACTIVE).count(),
        "definition": shared.definition, "invited": bool(member),
    })


@login_required
@require_POST
def template_publish(request, challenge_id):
    challenge = get_object_or_404(Challenge, pk=challenge_id, user=request.user)
    services.publish_template(request.user, challenge, request.POST.get("description", ""))
    messages.success(request, _("Published as a community template. Only the structure is shared — never your entries."))
    return redirect(f"{request.build_absolute_uri('/community/')}?tab=templates")


@login_required
@require_POST
def template_unpublish(request, pk):
    ChallengeTemplate.objects.filter(pk=pk, owner=request.user).delete()
    messages.success(request, _("Template removed from the community."))
    return redirect("/community/?tab=templates")

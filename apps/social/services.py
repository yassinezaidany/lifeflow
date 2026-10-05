"""Social business rules (friendships, shared challenges, community templates)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.analytics.services.progress import ProgressEngine
from apps.challenges.models import Challenge, ChallengeCategory, ChallengeTemplate
from apps.challenges.serializers import ChallengeCreateSerializer
from apps.challenges.services import challenge_definition, create_challenge
from apps.core.dates import user_today
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import Friendship, SharedChallenge, SharedChallengeMember

User = get_user_model()
F = Friendship.Status
M = SharedChallengeMember.Status


def display_name(user) -> str:
    return user.first_name or user.username


# ---------------------------------------------------------------------------- friends
def friends_of(user):
    pairs = Friendship.objects.filter(Q(from_user=user) | Q(to_user=user), status=F.ACCEPTED).values_list("from_user_id", "to_user_id")
    ids = {b if a == user.pk else a for a, b in pairs}
    return User.objects.filter(pk__in=ids, is_active=True).select_related("profile").order_by("first_name", "username")


def are_friends(a, b) -> bool:
    return Friendship.objects.filter(
        Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a), status=F.ACCEPTED
    ).exists()


FRIEND_REQUESTS_PER_HOUR = 30


@transaction.atomic
def send_friend_request(user, identifier: str) -> Friendship:
    from django.core.cache import cache

    key = f"friend-requests:{user.pk}"
    count = cache.get(key, 0)
    if count >= FRIEND_REQUESTS_PER_HOUR:
        raise ValidationError({"username": _("Too many friend requests. Try again later.")})
    cache.set(key, count + 1, 3600)
    identifier = (identifier or "").strip()
    if not identifier:
        raise ValidationError({"username": _("Enter a username or an e-mail address.")})
    lookup = Q(email__iexact=identifier) if "@" in identifier else Q(username__iexact=identifier)
    target = User.objects.filter(lookup, is_active=True).first()
    if target is None:
        raise ValidationError({"username": _("No LifeFlow user with this username or e-mail.")})
    if target.pk == user.pk:
        raise ValidationError({"username": _("You can't add yourself.")})
    existing = Friendship.objects.filter(Q(from_user=user, to_user=target) | Q(from_user=target, to_user=user)).first()
    if existing:
        if existing.status == F.ACCEPTED:
            raise ValidationError({"username": _("You are already friends.")})
        if existing.from_user_id == target.pk and existing.status == F.PENDING:
            return respond_to_request(existing, user, accept=True)  # they already asked you: accept
        # re-send a declined/pending request from me
        existing.from_user, existing.to_user, existing.status, existing.responded_at = user, target, F.PENDING, None
        existing.save()
        friendship = existing
    else:
        friendship = Friendship.objects.create(from_user=user, to_user=target)
    notify(target, Notification.Kind.SYSTEM, _("%(name)s wants to be your friend on LifeFlow") % {"name": display_name(user)},
           url="/community/", dedupe_key=f"friendreq:{friendship.pk}:{friendship.updated_at:%Y%m%d%H%M%S}")
    return friendship


@transaction.atomic
def respond_to_request(friendship: Friendship, user, accept: bool) -> Friendship:
    if friendship.to_user_id != user.pk or friendship.status != F.PENDING:
        raise PermissionDenied
    friendship.status = F.ACCEPTED if accept else F.DECLINED
    friendship.responded_at = timezone.now()
    friendship.save(update_fields=["status", "responded_at", "updated_at"])
    if accept:
        notify(friendship.from_user, Notification.Kind.SYSTEM, _("%(name)s accepted your friend request") % {"name": display_name(user)},
               url="/community/", dedupe_key=f"friendok:{friendship.pk}")
    return friendship


def remove_friend(user, other) -> None:
    Friendship.objects.filter(Q(from_user=user, to_user=other) | Q(from_user=other, to_user=user)).delete()


# ---------------------------------------------------------------------------- shared challenges
def _definition_for(challenge: Challenge) -> dict:
    definition = challenge_definition(challenge)
    definition["category_name"] = challenge.category.name if challenge.category else ""
    return definition


@transaction.atomic
def share_challenge(owner, challenge: Challenge) -> SharedChallenge:
    if challenge.user_id != owner.pk:
        raise PermissionDenied
    existing = SharedChallengeMember.objects.filter(challenge=challenge, status=M.ACTIVE).select_related("shared").first()
    if existing:
        return existing.shared
    shared = SharedChallenge.objects.create(
        owner=owner, name=challenge.name, description=challenge.description, icon=challenge.icon, color=challenge.color,
        definition=_definition_for(challenge), start_date=challenge.start_date, end_date=challenge.end_date,
    )
    SharedChallengeMember.objects.create(shared=shared, user=owner, challenge=challenge, status=M.ACTIVE, joined_at=timezone.now())
    return shared


def membership(shared: SharedChallenge, user) -> SharedChallengeMember | None:
    return shared.members.filter(user=user).first()


def is_active_member(shared, user) -> bool:
    return shared.members.filter(user=user, status=M.ACTIVE).exists()


@transaction.atomic
def invite_friend(shared: SharedChallenge, inviter, friend) -> SharedChallengeMember:
    if not is_active_member(shared, inviter):
        raise PermissionDenied
    if not shared.is_active:
        raise ValidationError({"detail": _("This group challenge is closed.")})
    if not are_friends(inviter, friend):
        raise ValidationError({"user": _("You can only invite your friends.")})
    member, created = SharedChallengeMember.objects.get_or_create(shared=shared, user=friend, defaults={"invited_by": inviter})
    if member.status == M.ACTIVE:
        raise ValidationError({"user": _("Already a member.")})
    if not created:
        member.status, member.invited_by = M.INVITED, inviter
        member.save(update_fields=["status", "invited_by", "updated_at"])
    notify(friend, Notification.Kind.SYSTEM, _("%(name)s invited you to the challenge “%(challenge)s”") % {"name": display_name(inviter), "challenge": shared.name},
           url=f"/community/join/{shared.invite_code}/", dedupe_key=f"invite:{member.pk}:{member.updated_at:%Y%m%d%H%M}")
    return member


@transaction.atomic
def join_shared(shared: SharedChallenge, user) -> SharedChallengeMember:
    if not shared.is_active:
        raise ValidationError({"detail": _("This group challenge is closed.")})
    today = user_today(user)
    if shared.end_date and shared.end_date < today:
        raise ValidationError({"detail": _("This group challenge is already over.")})
    member = SharedChallengeMember.objects.select_for_update().filter(shared=shared, user=user).first()
    if member and member.status == M.ACTIVE:
        return member

    definition = dict(shared.definition)
    category = ChallengeCategory.objects.filter(user=user, name__iexact=definition.pop("category_name", "") or "-").first()
    payload = {
        "name": shared.name, "description": shared.description, "icon": shared.icon, "color": shared.color,
        "category": category.pk if category else None,
        "start_date": max(today, shared.start_date).isoformat(),
        "end_date": shared.end_date.isoformat() if shared.end_date else None,
        "fields": [{**f, "ref": f.get("key") or f["label"]} for f in definition.get("fields", [])],
        "goal": definition.get("goal", {}), "schedule": definition.get("schedule", {}),
    }
    serializer = ChallengeCreateSerializer(data=payload, context={"request": type("R", (), {"user": user})()})
    serializer.is_valid(raise_exception=True)
    challenge = create_challenge(user, serializer.validated_data)

    member = member or SharedChallengeMember(shared=shared, user=user)
    member.challenge, member.status, member.joined_at = challenge, M.ACTIVE, timezone.now()
    member.save()
    if shared.owner_id != user.pk:
        notify(shared.owner, Notification.Kind.SYSTEM, _("%(name)s joined “%(challenge)s”") % {"name": display_name(user), "challenge": shared.name},
               url=f"/community/shared/{shared.pk}/", dedupe_key=f"joined:{member.pk}:{member.joined_at:%Y%m%d%H%M}")
    return member


@transaction.atomic
def decline_invitation(shared: SharedChallenge, user) -> None:
    shared.members.filter(user=user, status=M.INVITED).delete()


@transaction.atomic
def leave_shared(shared: SharedChallenge, user) -> None:
    """The member keeps their personal challenge and all entries."""
    member = membership(shared, user)
    if member is None or member.status != M.ACTIVE:
        return
    if shared.owner_id == user.pk:
        raise ValidationError({"detail": _("You created this group challenge: close it instead of leaving.")})
    member.status, member.challenge = M.LEFT, None
    member.save(update_fields=["status", "challenge", "updated_at"])


@transaction.atomic
def close_shared(shared: SharedChallenge, user) -> None:
    """Owner closes the group. Members keep their personal challenges."""
    if shared.owner_id != user.pk:
        raise PermissionDenied
    shared.delete()


def leaderboard(shared: SharedChallenge, viewer) -> list[dict]:
    rows = []
    members = shared.members.filter(status=M.ACTIVE).select_related("user", "user__profile", "challenge")
    for m in members:
        row = {"member_id": m.pk, "user_id": m.user_id, "name": display_name(m.user), "username": m.user.username,
               "initials": m.user.initials, "is_me": m.user_id == viewer.pk, "is_owner": m.user_id == shared.owner_id,
               "hidden": not m.share_progress and m.user_id != viewer.pk}
        challenge = m.challenge
        if challenge is not None and not row["hidden"]:
            challenge = ProgressEngine.prefetch(Challenge.objects.filter(pk=challenge.pk)).first()
            if challenge is not None:
                r = ProgressEngine(m.user).evaluate(challenge)
                row.update({
                    "progress": round(r.progress_capped, 1) if r.progress is not None else None,
                    "completion_rate": round(r.completion_rate, 1) if r.completion_rate is not None else None,
                    "current_streak": r.current_streak, "best_streak": r.best_streak, "streak_unit": r.streak_unit,
                    "status": r.status.value, "done_today": bool(r.today.get("done")),
                })
        rows.append(row)
    rows.sort(key=lambda r: (r["hidden"], -(r.get("completion_rate") or 0), -(r.get("current_streak") or 0)))
    return rows


def shared_for_user(user):
    return SharedChallenge.objects.filter(members__user=user, members__status__in=[M.ACTIVE, M.INVITED]).annotate(
        member_count=Count("members", filter=Q(members__status=M.ACTIVE), distinct=True)
    ).distinct()


# ---------------------------------------------------------------------------- community templates
@transaction.atomic
def publish_template(user, challenge: Challenge, description: str = "") -> ChallengeTemplate:
    if challenge.user_id != user.pk:
        raise PermissionDenied
    base = slugify(challenge.name)[:60] or "challenge"
    slug, i = base, 2
    while ChallengeTemplate.objects.filter(owner=user, slug=slug).exists():
        slug, i = f"{base}-{i}", i + 1
    duration = (challenge.end_date - challenge.start_date).days + 1 if challenge.end_date else None
    return ChallengeTemplate.objects.create(
        owner=user, slug=slug, name=challenge.name, description=(description or challenge.description)[:1000],
        icon=challenge.icon, color=challenge.color, category_name=challenge.category.name if challenge.category else "",
        duration_days=duration, definition=challenge_definition(challenge), is_public=True,
    )


def community_templates():
    return (
        ChallengeTemplate.objects.filter(is_public=True, owner__isnull=False, owner__is_active=True)
        .select_related("owner").annotate(uses=Count("challenges")).order_by("-uses", "-created_at")
    )

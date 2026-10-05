from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.challenges.models import Challenge, ChallengeTemplate
from apps.notifications.models import Notification
from apps.social import services
from apps.social.models import Friendship, SharedChallenge, SharedChallengeMember
from apps.tracking.models import ChallengeEntry

from .factories import add_entry, make_challenge, make_user

pytestmark = pytest.mark.django_db


def befriend(a, b):
    f = services.send_friend_request(a, b.username)
    services.respond_to_request(f, b, accept=True)


class TestFriends:
    def test_request_accept_and_list(self, user, other_user):
        f = services.send_friend_request(user, "BOB")  # case-insensitive username
        assert f.status == "pending" and Notification.objects.filter(user=other_user).exists()
        services.respond_to_request(f, other_user, accept=True)
        assert list(services.friends_of(user)) == [other_user] and list(services.friends_of(other_user)) == [user]
        assert Notification.objects.filter(user=user, title__icontains="accepted").exists()

    def test_by_email_and_reverse_request_auto_accepts(self, user, other_user):
        services.send_friend_request(other_user, user.username)
        f = services.send_friend_request(user, "bob@example.com")
        assert f.status == Friendship.Status.ACCEPTED

    @pytest.mark.parametrize("identifier", ["", "nobody", "alice"])
    def test_invalid_requests(self, user, identifier):
        with pytest.raises(ValidationError):
            services.send_friend_request(user, identifier)

    def test_already_friends_and_only_recipient_can_answer(self, user, other_user):
        f = services.send_friend_request(user, other_user.username)
        with pytest.raises(PermissionDenied):
            services.respond_to_request(f, user, accept=True)
        services.respond_to_request(f, other_user, accept=True)
        with pytest.raises(ValidationError):
            services.send_friend_request(user, other_user.username)

    def test_decline_and_remove(self, user, other_user):
        f = services.send_friend_request(user, other_user.username)
        services.respond_to_request(f, other_user, accept=False)
        assert not services.are_friends(user, other_user)
        befriend(user, other_user)
        services.remove_friend(other_user, user)
        assert not services.are_friends(user, other_user)

    def test_rate_limit(self, user, settings):
        from django.core.cache import cache
        cache.clear()
        targets = [make_user(f"t{i}") for i in range(services.FRIEND_REQUESTS_PER_HOUR)]
        for t in targets:
            services.send_friend_request(user, t.username)
        extra = make_user("one_more")
        with pytest.raises(ValidationError):
            services.send_friend_request(user, extra.username)
        cache.clear()

    def test_web_flow(self, web, user, other_user):
        from django.test import Client
        assert web.post(reverse("social:friend_add"), {"username": "bob"}).status_code == 302
        f = Friendship.objects.get()
        bob = Client()
        bob.force_login(other_user)
        bob.post(reverse("social:friend_respond", args=[f.pk]), {"action": "accept"})
        assert services.are_friends(user, other_user)
        page = web.get(reverse("social:community")).content.decode()
        assert "@bob" in page


class TestSharedChallenges:
    @pytest.fixture
    def setup(self, user, other_user):
        befriend(user, other_user)
        c = make_challenge(user, name="Read together", start=date(2026, 1, 1),
                           fields=[{"label": "Pages", "key": "pages", "field_type": "integer", "unit": "pages"}],
                           goal={"metric": "pages", "period": "daily", "aggregation": "sum", "target": 10})
        shared = services.share_challenge(user, c)
        return c, shared

    def test_share_invite_join_and_leaderboard(self, setup, user, other_user):
        c, shared = setup
        assert services.share_challenge(user, c).pk == shared.pk  # idempotent
        services.invite_friend(shared, user, other_user)
        assert SharedChallengeMember.objects.get(user=other_user).status == "invited"
        member = services.join_shared(shared, other_user)
        copy = member.challenge
        assert copy.user == other_user and copy.name == "Read together" and copy.pk != c.pk
        assert copy.fields.get().key == "pages" and copy.current_goal.target == 10
        add_entry(copy, copy.start_date, pages=12)
        rows = services.leaderboard(shared, user)
        assert {r["username"] for r in rows} == {"alice", "bob"}
        assert all("entries" not in r and "note" not in r for r in rows)

    def test_cannot_invite_non_friend(self, setup, user):
        _c, shared = setup
        stranger = make_user("stranger")
        with pytest.raises(ValidationError):
            services.invite_friend(shared, user, stranger)

    def test_privacy_toggle_hides_figures(self, setup, user, other_user):
        _c, shared = setup
        member = services.join_shared(shared, other_user)
        member.share_progress = False
        member.save()
        bob_row = next(r for r in services.leaderboard(shared, user) if r["username"] == "bob")
        assert bob_row["hidden"] and "completion_rate" not in bob_row
        own = next(r for r in services.leaderboard(shared, other_user) if r["username"] == "bob")
        assert not own["hidden"]  # you always see your own figures

    def test_non_members_get_404(self, setup, client, api):
        _c, shared = setup
        outsider = make_user("outsider")
        client.force_login(outsider)
        assert client.get(reverse("social:shared", args=[shared.pk])).status_code == 404
        from rest_framework.test import APIClient
        a = APIClient()
        a.force_authenticate(outsider)
        assert a.get(f"/api/social/shared/{shared.pk}/leaderboard/").status_code == 404
        assert api.get(f"/api/social/shared/{shared.pk}/leaderboard/").status_code == 200

    def test_join_by_link_and_leave_keeps_data(self, setup, client, other_user):
        _c, shared = setup
        client.force_login(other_user)
        assert client.get(reverse("social:join", args=[shared.invite_code])).status_code == 200
        client.post(reverse("social:join", args=[shared.invite_code]), {"action": "join"})
        member = SharedChallengeMember.objects.get(user=other_user)
        copy = member.challenge
        add_entry(copy, copy.start_date, pages=3)
        client.post(reverse("social:shared_leave", args=[shared.pk]))
        member.refresh_from_db()
        assert member.status == "left" and Challenge.objects.filter(pk=copy.pk).exists()
        assert ChallengeEntry.objects.filter(challenge=copy).count() == 1
        assert client.get(reverse("social:shared", args=[shared.pk])).status_code == 404

    def test_owner_close_keeps_member_challenges(self, setup, user, other_user):
        c, shared = setup
        copy = services.join_shared(shared, other_user).challenge
        with pytest.raises(PermissionDenied):
            services.close_shared(shared, other_user)
        services.close_shared(shared, user)
        assert not SharedChallenge.objects.exists()
        assert Challenge.objects.filter(pk__in=[c.pk, copy.pk]).count() == 2

    def test_owner_cannot_leave(self, setup, user):
        _c, shared = setup
        with pytest.raises(ValidationError):
            services.leave_shared(shared, user)

    def test_closed_or_finished_group_cannot_be_joined(self, setup, other_user):
        _c, shared = setup
        shared.end_date = date(2020, 1, 31)
        shared.start_date = date(2020, 1, 1)
        shared.save()
        with pytest.raises(ValidationError):
            services.join_shared(shared, other_user)

    def test_pages(self, setup, web):
        _c, shared = setup
        assert web.get(reverse("social:shared", args=[shared.pk])).status_code == 200
        for tab in ("friends", "groups", "templates"):
            assert web.get(reverse("social:community") + f"?tab={tab}").status_code == 200
        assert web.get("/api/social/friends/").status_code == 200 and web.get("/api/social/shared/").status_code == 200


class TestCommunityTemplates:
    def test_publish_use_unpublish(self, user, other_user, client):
        c = make_challenge(user, name="Morning pages", start=date(2026, 1, 1), end=date(2026, 1, 30))
        add_entry(c, date(2026, 1, 2), amount=5)
        tpl = services.publish_template(user, c, "Write every morning")
        assert tpl.is_public and tpl.duration_days == 30 and "entries" not in tpl.definition
        assert tpl in services.community_templates()
        client.force_login(other_user)
        page = client.get(reverse("social:community") + "?tab=templates").content.decode()
        assert "Morning pages" in page
        assert client.get(reverse("challenges:create") + f"?template_id={tpl.pk}").status_code == 200
        # only the author can unpublish
        client.post(reverse("social:template_unpublish", args=[tpl.pk]))
        assert ChallengeTemplate.objects.filter(pk=tpl.pk).exists()
        services.publish_template(user, c)  # second publish gets a unique slug
        assert ChallengeTemplate.objects.filter(owner=user).count() == 2

    def test_cannot_publish_others_challenge(self, user, other_user):
        c = make_challenge(user, start=date(2026, 1, 1))
        with pytest.raises(PermissionDenied):
            services.publish_template(other_user, c)

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import api as accounts
from apps.challenges import api as challenges
from apps.dashboard import api as dashboard
from apps.journal import api as journal
from apps.notifications import api as notifications
from apps.planner import api as planner
from apps.reports import api as reports
from apps.social import api as social
from apps.tracking import api as tracking

router = DefaultRouter()
router.register("challenges", challenges.ChallengeViewSet, basename="challenge")
router.register("challenge-categories", challenges.ChallengeCategoryViewSet, basename="challenge-category")
router.register("challenge-templates", challenges.ChallengeTemplateViewSet, basename="challenge-template")
router.register("rest-days", challenges.RestDayViewSet, basename="rest-day")
router.register("entries", tracking.EntryViewSet, basename="entry")
router.register("planner/activities", planner.PlannedActivityViewSet, basename="activity")
router.register("planner/rules", planner.RecurringRuleViewSet, basename="rule")
router.register("planner/templates", planner.PlannerTemplateViewSet, basename="planner-template")
router.register("planner/categories", planner.ActivityCategoryViewSet, basename="activity-category")
router.register("journal/weekly-reviews", journal.WeeklyReviewViewSet, basename="weekly-review")
router.register("journal", journal.JournalEntryViewSet, basename="journal")
router.register("reports", reports.ReportViewSet, basename="report")
router.register("notifications", notifications.NotificationViewSet, basename="notification")

entry_list = tracking.EntryViewSet.as_view({"get": "list", "post": "create"})

app_name = "api"
urlpatterns = [
    path("auth/register/", accounts.register, name="register"),
    path("auth/login/", accounts.login_view, name="login"),
    path("auth/logout/", accounts.logout_view, name="logout"),
    path("auth/me/", accounts.me, name="me"),
    path("auth/password/", accounts.change_password, name="change-password"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("challenges/<int:challenge_pk>/entries/", entry_list, name="challenge-entries"),
    path("planner/", planner.planner_day, name="planner-day"),
    path("planner/today/", planner.planner_today, name="planner-today"),
    path("planner/week/", planner.planner_week, name="planner-week"),
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("calendar/", dashboard.calendar, name="calendar"),
    path("calendar/day/", dashboard.calendar_day, name="calendar-day"),
    path("social/friends/", social.friends, name="social-friends"),
    path("social/shared/", social.shared_list, name="social-shared"),
    path("social/shared/<int:pk>/leaderboard/", social.shared_leaderboard, name="social-leaderboard"),
    path("", include(router.urls)),
]

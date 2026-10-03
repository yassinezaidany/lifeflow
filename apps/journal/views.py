from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.accounts.forms import StyledFormMixin
from apps.challenges.models import Challenge
from apps.core.dates import parse_date
from apps.dashboard.services import build_weekly_review

from .models import JournalEntry, WeeklyReview


class JournalForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ["date", "title", "content", "mood", "challenge"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), "content": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["challenge"].queryset = Challenge.objects.filter(user=user)
        self.fields["challenge"].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.scope = JournalEntry.Scope.CHALLENGE if obj.challenge_id else JournalEntry.Scope.DAY
        if commit:
            obj.save()
        return obj


class ReviewForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WeeklyReview
        fields = ["went_well", "difficult", "improve", "rating"]
        labels = {
            "went_well": gettext_lazy("What went well?"),
            "difficult": gettext_lazy("What was difficult?"),
            "improve": gettext_lazy("What should I improve?"),
            "rating": gettext_lazy("How was your week? (1–5)"),
        }
        widgets = {"rating": forms.NumberInput(attrs={"min": 1, "max": 5})}


@login_required
def journal_list(request):
    qs = JournalEntry.objects.filter(user=request.user).select_related("challenge")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(content__icontains=q) | Q(title__icontains=q))
    day = parse_date(request.GET.get("date"))
    if day:
        qs = qs.filter(date=day)
    challenge = request.GET.get("challenge")
    if challenge and challenge.isdigit():
        qs = qs.filter(challenge_id=int(challenge))
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(request, "journal/list.html", {
        "page": page, "q": q, "day": day,
        "challenges": Challenge.objects.filter(user=request.user, journal_entries__isnull=False).distinct(),
        "challenge": challenge,
    })


@login_required
def journal_detail(request, pk=None):
    entry = get_object_or_404(JournalEntry, pk=pk, user=request.user) if pk else None
    form = JournalForm(request.POST or None, instance=entry, user=request.user,
                       initial={"date": parse_date(request.GET.get("date"))} if not entry else None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, _("Journal entry saved."))
        return redirect("journal:list")
    return render(request, "journal/detail.html", {"form": form, "entry": entry})


@login_required
@require_POST
def journal_delete(request, pk):
    get_object_or_404(JournalEntry, pk=pk, user=request.user).delete()
    messages.success(request, _("Journal entry deleted."))
    return redirect("journal:list")


@login_required
def weekly_review(request):
    data = build_weekly_review(request.user, parse_date(request.GET.get("week")))
    form = ReviewForm(request.POST or None, instance=data["review"])
    if request.method == "POST" and form.is_valid():
        review = form.save(commit=False)
        review.user = request.user
        review.week_start = data["start"]
        if review.rating is not None and not 1 <= review.rating <= 5:
            form.add_error("rating", _("Choose a value between 1 and 5."))
        else:
            review.save()
            messages.success(request, _("Weekly review saved."))
            return redirect(f"{request.path}?week={data['start'].isoformat()}")
    data["form"] = form
    return render(request, "journal/review.html", data)

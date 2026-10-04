"""Strings used by the JavaScript layer, translated server-side and injected as JSON."""
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N

JS_STRINGS = [
    N("Network error. Check your connection."), N("Your session expired. Please sign in again."),
    N("Something went wrong. Please try again."), N("Are you sure?"), N("Confirm"), N("Progress recorded"),
    N("Note saved"), N("Recurring activity created"), N("Activity added"), N("Activity added (overlaps another activity)"),
    N("Series updated"), N("Activity updated"), N("Record this activity in your challenge “%s”?"), N("Activity completed"),
    N("Review & record"), N("Status updated"), N("Activity rescheduled"), N("Activity duplicated"),
    N("Delete the whole series? Past activities are kept."), N("Delete this activity?"), N("Delete"), N("Deleted"),
    N("Moved — overlaps %s"), N("Activity moved"), N("Choose at least one day."), N("%s activities added"),
    N("Give the template a name."), N("Template saved"), N("Done"), N("Amount"), N("pages"), N("Duration"), N("Distance"),
    N("km"), N("Value"), N("sessions"), N("days"), N("minutes"), N("per day"), N("per week"), N("per month"), N("in total"),
    N("min."), N("per entry"), N("Every day"), N("Every %s days"), N("Give your challenge a name."),
    N("Choose what you want to measure."), N("Name this field."), N("The target must be greater than zero."),
    N("Select at least one day."), N("End date must be on or after the start date."), N("Challenge created"), N("Saved"),
    N("Goal updated — earlier days keep the previous goal"), N("Schedule updated"), N("Field added"), N("Field renamed"),
    N("Remove this field? Recorded values are kept in history."), N("Remove"), N("Field removed"), N("Milestone added"),
    N("Delete this challenge and all its entries? This cannot be undone. Archiving keeps your history."),
    N("Delete forever"), N("Delete this entry?"), N("Entry deleted"), N("Entry updated"),
    N("You're offline. This data isn't available on this device yet."), N("An offline entry could not be saved:"),
    N("%s offline item(s) synced"), N("Saved offline — it will sync automatically"), N("LifeFlow is installed"),
    N("Notifications enabled on this device"), N("Notifications are blocked in your browser settings."),
    N("Push notifications are not available on this browser."), N("Notifications disabled on this device"),
    N("Describe your challenge first."), N("Suggestion applied — review each step before creating."),
]


def js_translations() -> dict:
    return {s: _(s) for s in JS_STRINGS}

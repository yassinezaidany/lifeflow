from django.db import migrations


def forwards(apps, schema_editor):
    from apps.challenges.system_templates import sync_system_templates

    sync_system_templates(apps.get_model("challenges", "ChallengeTemplate"))


def backwards(apps, schema_editor):
    apps.get_model("challenges", "ChallengeTemplate").objects.filter(owner__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("challenges", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]

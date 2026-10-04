from django.db import migrations


def forwards(apps, schema_editor):
    from apps.challenges.system_templates import sync_system_templates

    sync_system_templates(apps.get_model("challenges", "ChallengeTemplate"))


class Migration(migrations.Migration):
    dependencies = [("challenges", "0005_time_goals")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]

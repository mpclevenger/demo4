"""Controls move to the "how to build it" shape.

Schema: controls lose `criteria` and `timings` and gain `choosing_people`; the evidence rules (the
generic evidence groups that used to be added to every control page) are removed, because nothing else
used them.

Data: each old step becomes {"do": <old text>, "evidence": {"keep": <old evidence>}} when it had
evidence, and {"do": <old text>} when it had none. The old step role and part are dropped. Old criteria
and timings are dropped too. The site is not live yet, so losing them from old versions is accepted:
the content files are being rewritten into the new shape and the next sync brings the new content in.
Going back keeps the schema steps but cannot restore what was dropped, so the data step does nothing in reverse.
"""

from django.db import migrations, models


def convert_steps(apps, schema_editor):
    ControlVersion = apps.get_model("rcm", "ControlVersion")
    for version in ControlVersion.objects.all():
        new_steps = [_new_step(step) for step in version.steps if isinstance(step, dict)]
        new_steps = [step for step in new_steps if step["do"]]
        if new_steps != version.steps:
            ControlVersion.objects.filter(pk=version.pk).update(steps=new_steps)


def _new_step(old):
    if "do" in old:  # already in the new shape
        return old
    do = str(old.get("text") or "").strip()
    evidence = str(old.get("evidence") or "").strip()
    return {"do": do, "evidence": {"keep": evidence}} if evidence else {"do": do}


class Migration(migrations.Migration):

    dependencies = [
        ("rcm", "0007_control_timings"),
    ]

    operations = [
        migrations.RunPython(convert_steps, migrations.RunPython.noop),
        migrations.RemoveField(model_name="controlversion", name="criteria"),
        migrations.RemoveField(model_name="controlversion", name="timings"),
        migrations.AddField(
            model_name="controlversion",
            name="choosing_people",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Notes on choosing who performs and who reviews: {"performer": [str], "reviewer": [str], "small_team": str}.',
            ),
        ),
        migrations.AlterField(
            model_name="controlversion",
            name="steps",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='How to build it, in order: [{"do": str, "how": str, "weigh": [str], "policy": str, "evidence": {"keep": str, "shows": [str]}, "commands": [{"platform": str, "note": str, "code": str}]}]. Only do is required.',
            ),
        ),
        migrations.AlterField(
            model_name="controlversion",
            name="why",
            field=models.TextField(help_text="The benefit of having this control, in two or three sentences."),
        ),
        migrations.DeleteModel(name="EvidenceRuleVersion"),
        migrations.DeleteModel(name="EvidenceRule"),
    ]

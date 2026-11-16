"""Gives TRAC its own codes, so they are never mixed up with the firm's SOX control IDs.

Change management MC becomes CM, access management MA becomes AM, and operations and jobs OP
becomes MO (for monitoring). The numbers stay. This renames, in one go:

- control IDs (MC-01 to CM-01) and risk IDs (R-MC-01 to R-CM-01);
- the topic prefix (MC to CM) and the ID counters (MC and R-MC);
- the TRAC risk IDs listed on each driver (drivers.json's trac_risks).

Safe to run on an empty database, and on one that already has the new IDs: a rename is skipped when
the new ID or prefix already exists. An earlier draft of this change used OJ for operations and
jobs; those are renamed to MO too. Running it backwards renames everything back.
"""

from django.db import migrations

NEW_FOR_OLD = {"MC": "CM", "MA": "AM", "OP": "MO", "OJ": "MO"}  # OJ: the short-lived first choice
OLD_FOR_NEW = {"CM": "MC", "AM": "MA", "MO": "OP"}


def _renamed(text, swap):
    """`text` with its prefix swapped (MC-01 to CM-01, R-MC-01 to R-CM-01), or None if it has none."""
    risk = "R-" if text.startswith("R-") else ""
    prefix, dash, number = text[len(risk):].partition("-")
    return f"{risk}{swap[prefix]}-{number}" if dash and prefix in swap else None


def _rename_field(model, field, swap):
    """Rename one unique text column; skips a row whose new value is already taken."""
    taken = set(model.objects.values_list(field, flat=True))
    for row in model.objects.all():
        new = _renamed(getattr(row, field), swap)
        if new and new not in taken:
            setattr(row, field, new)
            row.save(update_fields=[field])
            taken.add(new)


def _rename_prefixes(model, field, swap):
    """Rename prefixes kept on their own (MC, and R-MC for risk counters)."""
    taken = set(model.objects.values_list(field, flat=True))
    for row in model.objects.all():
        old = getattr(row, field)
        bare = old.removeprefix("R-")
        if bare in swap and (new := old[: len(old) - len(bare)] + swap[bare]) not in taken:
            setattr(row, field, new)
            row.save(update_fields=[field])
            taken.add(new)


def _rename_driver_risks(DriverVersion, swap):
    """Rename the TRAC risk IDs in each driver's list. Updates in place: the driver versions are already approved."""
    for version in DriverVersion.objects.all():
        renamed = [_renamed(i, swap) or i for i in version.trac_risks]
        if renamed != version.trac_risks:
            DriverVersion.objects.filter(pk=version.pk).update(trac_risks=renamed)


def rename(apps, swap):
    _rename_field(apps.get_model("rcm", "Control"), "ident", swap)
    _rename_field(apps.get_model("rcm", "Risk"), "ident", swap)
    _rename_prefixes(apps.get_model("rcm", "IdSequence"), "key", swap)
    _rename_prefixes(apps.get_model("topics", "Topic"), "id_prefix", swap)
    _rename_driver_risks(apps.get_model("rcm", "DriverVersion"), swap)


def forwards(apps, schema_editor):
    rename(apps, NEW_FOR_OLD)


def backwards(apps, schema_editor):
    rename(apps, OLD_FOR_NEW)


class Migration(migrations.Migration):

    dependencies = [
        ("rcm", "0008_control_build_steps"),
        ("topics", "0002_clock_icon"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]

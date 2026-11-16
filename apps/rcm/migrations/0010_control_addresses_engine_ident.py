"""Controls gain `addresses` (the engine risks a control addresses); engine risks gain `ident` (the engine's id, for example air.ops.02)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rcm", "0009_trac_own_codes")]

    operations = [
        migrations.AddField(
            model_name="controlversion",
            name="addresses",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="The risks this control addresses: ids of the risk engine's risks, for example air.ops.02. Empty until Tech Risk maps them.",
            ),
        ),
        migrations.AddField(
            model_name="enginerisk",
            name="ident",
            field=models.CharField(blank=True, db_index=True, default="", help_text="The engine's id for the risk, for example air.ops.02. Empty when the files give none.", max_length=80),
        ),
    ]

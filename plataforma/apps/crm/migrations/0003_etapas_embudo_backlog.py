from django.db import migrations, models

# Alinea el embudo con el Product Backlog (PC-PRO-01): se elimina "Contactado" y "Reunión",
# se agregan "Diagnóstico agendado" y "En negociación".
MAPA = {"contactado": "nuevo", "reunion": "diagnostico"}
INVERSO = {"nuevo": "nuevo", "diagnostico": "reunion", "negociacion": "cotizacion_enviada"}


def adelante(apps, schema_editor):
    Prospecto = apps.get_model("crm", "Prospecto")
    for antes, despues in MAPA.items():
        Prospecto.objects.filter(etapa=antes).update(etapa=despues)


def atras(apps, schema_editor):
    Prospecto = apps.get_model("crm", "Prospecto")
    for antes, despues in INVERSO.items():
        if antes != despues:
            Prospecto.objects.filter(etapa=antes).update(etapa=despues)


class Migration(migrations.Migration):

    dependencies = [("crm", "0002_prospecto_rut")]

    operations = [
        migrations.AlterField(
            model_name="prospecto",
            name="etapa",
            field=models.CharField(
                choices=[
                    ("nuevo", "Nuevo contacto"),
                    ("diagnostico", "Diagnóstico agendado"),
                    ("cotizacion_enviada", "Cotización enviada"),
                    ("negociacion", "En negociación"),
                    ("ganado", "Cerrado ganado"),
                    ("perdido", "Perdido"),
                ],
                db_index=True, default="nuevo", max_length=20,
            ),
        ),
        migrations.RunPython(adelante, atras),
    ]

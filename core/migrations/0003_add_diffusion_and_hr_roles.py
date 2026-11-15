from django.db import migrations


def add_roles(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    db = schema_editor.connection.alias
    for name, description in (
        ("difusion", "Gestión de difusión y archivos compartidos"),
        ("recursos_humanos", "Gestión de recursos humanos"),
    ):
        Role.objects.using(db).get_or_create(
            name=name, defaults={"description": description, "active": True}
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0002_project_tools")]
    operations = [migrations.RunPython(add_roles, migrations.RunPython.noop)]

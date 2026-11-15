from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def group_existing_expenses(apps, schema_editor):
    Expense = apps.get_model("core", "Expense")
    Purchase = apps.get_model("core", "Purchase")
    for expense in Expense.objects.filter(purchase__isnull=True).iterator():
        purchase = Purchase.objects.create(
            date=expense.date,
            category=expense.category,
            responsible=expense.responsible,
            notes=expense.notes,
            registered_by_id=expense.registered_by_id,
        )
        Expense.objects.filter(pk=expense.pk).update(purchase_id=purchase.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_shared_asset_trash"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_column="fecha")),
                ("category", models.TextField(db_column="categoria", default="")),
                ("responsible", models.TextField(db_column="responsable", default="")),
                ("notes", models.TextField(db_column="notas", default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_column="creado_en")),
                ("registered_by", models.ForeignKey(blank=True, db_column="registrado_por", null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "compras_financieras"},
        ),
        migrations.AddField(
            model_name="expense",
            name="purchase",
            field=models.ForeignKey(blank=True, db_column="compra_id", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.purchase"),
        ),
        migrations.RunPython(group_existing_expenses, migrations.RunPython.noop),
    ]

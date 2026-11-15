from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0004_remove_hourrecord_activity_remove_assignment_period_and_more")]
    operations = [
        migrations.CreateModel(
            name="SharedAssetTrash",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("asset_id", models.BigIntegerField(db_index=True)),
                ("name", models.TextField(db_column="nombre")),
                ("file", models.TextField(db_column="archivo", unique=True)),
                ("content_type", models.TextField(db_column="tipo")),
                ("bytes", models.BigIntegerField()),
                ("original_created_at", models.DateTimeField(db_column="creado_en_original")),
                ("deleted_at", models.DateTimeField(auto_now_add=True, db_column="eliminado_en")),
                ("deleted_by", models.ForeignKey(blank=True, db_column="eliminado_por", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trashed_assets", to="core.user")),
                ("uploaded_by", models.ForeignKey(blank=True, db_column="subido_por", null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.user")),
            ],
            options={"db_table": "assets_papelera"},
        ),
    ]

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

class User(AbstractBaseUser):
    username = models.CharField(max_length=150, unique=True, db_column="nombre_usuario")
    password = models.CharField(max_length=128, db_column="password_hash")
    last_login = models.DateTimeField(blank=True, null=True, db_column="ultimo_acceso")
    date_joined = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    is_active = models.BooleanField(default=True, db_column="activo")
    objects = UserManager()
    USERNAME_FIELD = "username"
    approved = models.BooleanField(default=True, db_column="aprobado")
    person = models.OneToOneField("Person", null=True, blank=True, on_delete=models.SET_NULL, db_column="persona_id", related_name="account")
    roles = models.ManyToManyField("Role", through="UserRole", related_name="users")
    class Meta: db_table = "usuarios"
    def get_full_name(self):
        return self.person.first_name + " " + self.person.last_name if self.person_id else self.username
    def get_short_name(self):
        return self.username
    @property
    def is_staff(self):
        return self.role_name == "administrador"
    @property
    def is_superuser(self):
        return self.role_name == "administrador"
    def has_perm(self, perm, obj=None):
        return self.is_active and self.is_superuser
    def has_module_perms(self, app_label):
        return self.is_active and self.is_superuser
    @property
    def role_name(self):
        role = self.roles.order_by("id").first()
        return role.name if role else ""

class Person(models.Model):
    first_name = models.TextField(db_column="nombres")
    last_name = models.TextField(db_column="apellidos")
    email = models.TextField(null=True, blank=True, unique=True, db_column="correo")
    phone = models.TextField(null=True, blank=True, db_column="telefono")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    updated_at = models.DateTimeField(auto_now=True, db_column="actualizado_en")
    class Meta: db_table = "personas"

class Role(models.Model):
    name = models.TextField(unique=True, db_column="nombre")
    description = models.TextField(default="", db_column="descripcion")
    active = models.BooleanField(default=True, db_column="activo")
    class Meta: db_table = "roles"

    def save(self, *args, **kwargs):
        if self.description == "":
            self.description = {"administrador":"Administración general","presidente":"Acceso general de presidencia","vicepresidente":"Acceso general de vicepresidencia","finanzas":"Gestión financiera","proyectos":"Gestión de proyectos","difusion":"Gestión de difusión y archivos compartidos","recursos_humanos":"Gestión de recursos humanos"}.get(self.name, "")
        super().save(*args, **kwargs)

class Permission(models.Model):
    key = models.TextField(unique=True, db_column="clave")
    description = models.TextField(default="", db_column="descripcion")
    class Meta: db_table = "permisos"

class UserRole(models.Model):
    pk = models.CompositePrimaryKey("user", "role")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="usuario_id")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, db_column="rol_id")
    class Meta: db_table = "usuario_roles"

class RolePermission(models.Model):
    pk = models.CompositePrimaryKey("role", "permission")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, db_column="rol_id")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, db_column="permiso_id")
    class Meta: db_table = "rol_permisos"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="usuario_id")
    title = models.TextField(db_column="titulo")
    message = models.TextField(db_column="mensaje")
    read = models.BooleanField(default=False, db_column="leida")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creada_en")
    class Meta: db_table = "notificaciones"

class Audit(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="usuario_id")
    action = models.TextField(db_column="accion")
    entity = models.TextField(db_column="entidad")
    entity_id = models.BigIntegerField(null=True, blank=True, db_column="entidad_id")
    details = models.JSONField(default=dict, db_column="detalles")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    class Meta: db_table = "auditoria"

class Income(models.Model):
    concept = models.TextField(db_column="concepto")
    cents = models.BigIntegerField(db_column="monto_centavos")
    date = models.DateField(db_column="fecha")
    origin = models.TextField(default="", db_column="origen")
    responsible = models.TextField(default="", db_column="responsable")
    notes = models.TextField(default="", db_column="notas")
    registered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="registrado_por")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    class Meta:
        db_table = "ingresos_financieros"
        constraints = [models.CheckConstraint(condition=models.Q(cents__gt=0), name="ingreso_monto_positivo")]

class Expense(models.Model):
    concept = models.TextField(db_column="concepto")
    cents = models.BigIntegerField(db_column="monto_centavos")
    date = models.DateField(db_column="fecha")
    category = models.TextField(default="", db_column="categoria")
    responsible = models.TextField(default="", db_column="responsable")
    notes = models.TextField(default="", db_column="notas")
    registered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="registrado_por")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    class Meta:
        db_table = "egresos_financieros"
        constraints = [models.CheckConstraint(condition=models.Q(cents__gt=0), name="egreso_monto_positivo")]

class SharedAsset(models.Model):
    name = models.TextField(db_column="nombre")
    file = models.TextField(unique=True, db_column="archivo")
    content_type = models.TextField(db_column="tipo")
    bytes = models.BigIntegerField()
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="subido_por")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    class Meta: db_table = "assets_compartidos"

class SharedAssetTrash(models.Model):
    """Versión retirada de Drive, conservada para restaurar durante 15 días."""
    asset_id = models.BigIntegerField(db_index=True)
    name = models.TextField(db_column="nombre")
    file = models.TextField(unique=True, db_column="archivo")
    content_type = models.TextField(db_column="tipo")
    bytes = models.BigIntegerField()
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="subido_por")
    original_created_at = models.DateTimeField(db_column="creado_en_original")
    deleted_at = models.DateTimeField(auto_now_add=True, db_column="eliminado_en")
    deleted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="trashed_assets", db_column="eliminado_por")
    class Meta: db_table = "assets_papelera"

class ProjectDeadline(models.Model):
    title = models.CharField(max_length=200)
    due_date = models.DateField(db_column="fecha_limite")
    notes = models.TextField(default="")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

class ProjectInventory(models.Model):
    item = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(default="")
    updated_at = models.DateTimeField(auto_now=True)

class ProjectNote(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

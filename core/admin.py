from django.contrib import admin

from . import models


class ReadOnlyUserAdmin(admin.ModelAdmin):
    list_display = ("username", "person", "approved", "is_active")
    list_filter = ("approved", "is_active")
    search_fields = ("username", "person__first_name", "person__last_name")
    ordering = ("username",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(models.User, ReadOnlyUserAdmin)


@admin.register(models.Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "entity", "entity_id")
    list_filter = ("action", "entity", "created_at")
    search_fields = ("action", "entity", "details")
    readonly_fields = tuple(field.name for field in models.Audit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    models.Person, models.Role, models.Permission,
    models.Notification, models.Income, models.Purchase, models.Expense, models.SharedAsset,
    models.ProjectDeadline, models.ProjectInventory, models.ProjectNote,
):
    admin.site.register(model)

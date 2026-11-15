import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from core.models import Role, Person

class Command(BaseCommand):
    help = "Crea la cuenta administrativa inicial; --reset-password aplica ADMIN_PASSWORD a una cuenta existente."

    def add_arguments(self, parser):
        parser.add_argument("--reset-password", action="store_true", help="Restablece la contraseña administrativa al valor de ADMIN_PASSWORD.")

    def handle(self, *args, **options):
        username=os.getenv("ADMIN_USER", "").strip(); password=os.getenv("ADMIN_PASSWORD", "")
        if not username and not password:return
        if not username or not 10 <= len(password.encode()) <= 72:raise CommandError("Define ADMIN_USER y un ADMIN_PASSWORD de entre 10 y 72 bytes.")
        person,_=Person.objects.get_or_create(email="admin@lps.local",defaults={"first_name":"Administración","last_name":"LPS"})
        role=Role.objects.get(name="administrador")
        user,created=get_user_model().objects.get_or_create(username=username,defaults={"person":person,"is_active":True,"approved":True})
        user.person=person;user.is_active=True;user.approved=True
        if created or options["reset_password"]:user.set_password(password)
        user.save()
        user.roles.add(role)
        self.stdout.write(self.style.SUCCESS("Cuenta administrativa lista."))

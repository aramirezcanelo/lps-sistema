"""Elimina archivos cuya retención de 15 días ya venció."""
from django.core.management.base import BaseCommand
from core.views import purge_expired_assets


class Command(BaseCommand):
    help = "Purga los archivos de Drive que llevan 15 días o más en la papelera."

    def handle(self, *args, **options):
        purge_expired_assets()
        self.stdout.write(self.style.SUCCESS("Papelera de Drive depurada."))

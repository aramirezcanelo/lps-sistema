from django.contrib.auth.backends import ModelBackend
import bcrypt
import re
from django.utils import timezone
from .models import User

class LegacyBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        username = (username or kwargs.get("usuario") or "").strip()
        if not username or not password or len(username.encode()) > 100 or len(password.encode()) > 72:
            return None
        try:
            user = User.objects.get(username=username, is_active=True, approved=True)
        except User.DoesNotExist:
            return None
        role = user.role_name
        if role == "administrador" and len(password.encode()) < 10:
            return None
        if role in ("presidente", "vicepresidente") and not re.fullmatch(r"[0-9]{4}", password):
            return None
        if user.password.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                valid = bcrypt.checkpw(password.encode(), user.password.encode())
            except (ValueError, TypeError):
                valid = False
            if valid:
                user.set_password(password)
                user.save(update_fields=["password"])
        elif user.check_password(password):
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
        if user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
            return user if user.is_active and user.approved else None
        except User.DoesNotExist:
            return None

def modules(request):
    from .views import modules_for_role
    role = getattr(request.user, "role_name", "") if request.user.is_authenticated else ""
    return {"Modules": modules_for_role(role), "User": {"Name": request.user.username, "Role": role}}

import csv
import io
import mimetypes
import os
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseRedirect, FileResponse
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from .forms import ExpenseForm, IncomeForm, ProjectDeadlineForm, ProjectInventoryForm, ProjectNoteForm

from .models import User, Role, Income, Expense, Purchase, SharedAsset, SharedAssetTrash, ProjectDeadline, ProjectInventory, ProjectNote

ADMIN = "administrador"
def modules_for_role(role):
    items = {
        "finance": {"Name": "Finanzas", "Path": "/finanzas", "Icon": "finance", "Description": "Egresos, comprobantes y seguimiento financiero."},
        "projects": {"Name": "Proyectos", "Path": "/proyectos", "Icon": "projects", "Description": "Deadlines, inventario y notas del equipo."},
        "assets": {"Name": "Drive", "Path": "/drive", "Icon": "document", "Description": "Archivos compartidos para consultar y descargar."},
    }
    admin_items=[{"Name":"Usuarios","Path":"/usuarios","Icon":"people","Description":"Aprueba cuentas y asigna roles."}]
    modules = [items["projects"], items["assets"]]
    if role in (ADMIN, "finanzas", "presidente", "vicepresidente"):
        modules.insert(0, items["finance"])
    if role == ADMIN:
        modules.insert(0, admin_items[0])
    return modules

def current_role(user):
    return user.role_name if user.is_authenticated else ""

def valid_password_for_role(password, role):
    if role.name == ADMIN:
        return 10 <= len(password.encode()) <= 72
    return bool(re.fullmatch(r"[0-9]{4}", password))

def see_other(url):
    return HttpResponseRedirect(url, status=303)

def form_feedback(path,message):
    return see_other(path+"?"+urlencode({"mensaje":message}))

def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise ValueError("invalid date")
    return date.fromisoformat(value)

def parse_id(value):
    if not re.fullmatch(r"[0-9]+", value or ""):
        raise ValueError("invalid id")
    result=int(value)
    if result < 1: raise ValueError("invalid id")
    return result

def invalidate_user_sessions(user_id, keep_session_key=None):
    from django.contrib.sessions.models import Session
    user_id=str(user_id)
    for session in Session.objects.all().iterator():
        try:
            session_user_id=session.get_decoded().get("_auth_user_id")
        except Exception:
            # Una sesión dañada no debe bloquear cambios de cuenta o de NIP.
            session.delete()
            continue
        if session_user_id == user_id and session.session_key != keep_session_key:
            session.delete()

def allowed(request, role):
    user_role = current_role(request.user)
    if not request.user.is_authenticated:
        target = request.get_full_path()
        return see_other("/login?" + urlencode({"next": target}))
    valid = user_role == ADMIN or role == "*" or user_role == role
    if role == "gestores_assets": valid = user_role in (ADMIN, "difusion")
    if user_role in ("presidente", "vicepresidente") and role not in (ADMIN, "administrador", "*"):
        valid = True
    # Todos los usuarios autenticados pueden consultar proyectos y Drive;
    # las acciones de edición se validan en sus vistas de escritura.
    if role in ("proyectos", "drive"): valid = True
    if not valid:
        return error_page(403, "Acceso restringido", "Tu cuenta no tiene permiso para consultar esta sección.", "/")
    return None

def error_page(code, title, message, back):
    return render_status("pages/error.html", code, {"Title": title, "Message": message, "Back": back, "Code": code})

def csrf_failure(request, reason=""):
    return error_page(403,"Solicitud bloqueada por seguridad","No se pudo verificar el formulario. Recarga la página e inténtalo de nuevo.","/")

def not_found(request, exception):
    import logging
    logging.getLogger("core").info("Page not found: %s", request.path)
    return error_page(404, "No encontramos esa página", "La dirección puede haber cambiado o ya no estar disponible.", "/")

def server_error(request):
    import logging
    logging.getLogger("core").error("Unhandled server error for %s", request.path)
    return error_page(500, "Ocurrió un error", "No fue posible completar la solicitud. Inténtalo de nuevo.", "/")

def health_check(request):
    return HttpResponse("ok", content_type="text/plain; charset=utf-8")

def render_status(template, status, context=None):
    from django.template.loader import get_template
    try:
        return HttpResponse(get_template(template).render(context or {}), status=status)
    except Exception:
        return HttpResponse("%s %s" % (status, (context or {}).get("Title", "Error")), status=status)

def base_context(request, **values):
    user = request.user
    role = current_role(user)
    role_labels = {ADMIN: "Administración", "finanzas": "Finanzas", "proyectos": "Proyectos", "difusion": "Difusión", "recursos_humanos": "Recursos Humanos", "presidente": "Presidencia", "vicepresidente": "Vicepresidencia"}
    return {"User": {"Name": user.username if user.is_authenticated else "", "Role": role, "RoleLabel": role_labels.get(role, "Integrante")}, "Modules": modules_for_role(role), **values}

def login_view(request):
    if request.method == "GET":
        if request.user.is_authenticated:
            return see_other("/")
        return render(request, "pages/login.html", {"Message": request.GET.get("error", ""), "Next": safe_next(request, request.GET.get("next", ""))})
    if request.method != "POST": return HttpResponse("Método no permitido.", status=405)
    if not request.POST: return HttpResponse("Solicitud inválida.", status=400)
    username, password = request.POST.get("usuario", "").strip(), request.POST.get("contrasena", "")
    next_url = safe_next(request, request.POST.get("next", ""))
    user = authenticate(request, username=username, password=password)
    if not user:
        message = "Usuario o contraseña incorrectos."
        if request.headers.get("HX-Request") == "true":
            return HttpResponse('<div class="alert alert-danger" role="alert">%s</div>' % message, status=401, content_type="text/html; charset=utf-8")
        query = {"error": message}
        if next_url: query["next"] = next_url
        return see_other("/login?" + urlencode(query))
    login(request, user)
    response_url = next_url or "/"
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204); response["HX-Redirect"] = response_url; return response
    return see_other(response_url)

def safe_next(request, value):
    from urllib.parse import urlsplit, unquote
    path = urlsplit(value).path
    decoded_path=unquote(path)
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()) and decoded_path.startswith("/") and not decoded_path.startswith("//") and "\\" not in decoded_path and decoded_path not in ("/login", "/registro"):
        return value
    return ""

def logout_view(request):
    gate=allowed(request,"*")
    if gate:return gate
    if request.method != "POST": return HttpResponse("Método no permitido.", status=405)
    logout(request)
    return see_other("/login")

def register(request):
    if request.method == "GET": return render(request, "pages/register.html", {"Sent": request.GET.get("enviado") == "1"})
    username, password = request.POST.get("usuario", "").strip(), request.POST.get("contrasena", "")
    if not username or len(username.encode()) > 100 or not re.fullmatch(r"[0-9]{4}", password):
        return HttpResponse("Completa los datos. El NIP debe tener exactamente 4 dígitos.", status=400)
    try:
        User.objects.create_user(username=username, password=password, is_active=False, approved=False)
    except IntegrityError:
        return HttpResponse("No se pudo enviar la solicitud. Ese usuario quizá ya está registrado.", status=409)
    return see_other("/registro?enviado=1")

def dashboard(request):
    gate = allowed(request, "*")
    if gate: return gate
    if request.path != "/": return error_page(404, "No encontramos esa página", "La dirección puede haber cambiado o ya no estar disponible.", "/")
    return render(request, "pages/dashboard.html", base_context(request, Title="Inicio"))

def action_error(status, title, message, back):
    return render_status("pages/error.html", status, {"Code": status, "Title": title, "Message": message, "Back": back})

def finance(request):
    gate=allowed(request,"finanzas")
    if gate: return gate
    if request.method!="GET": return HttpResponse("Método no permitido.",status=405)
    selected_date=request.GET.get("fecha","").strip()
    try: selected_day=parse_date(selected_date) if selected_date else None
    except ValueError: selected_day=None; selected_date=""
    incomes=Income.objects.order_by("-date","-id"); expenses=Expense.objects.select_related("purchase").order_by("-date","-id")
    if selected_day:
        incomes=incomes.filter(date=selected_day)
        expenses=expenses.filter(date=selected_day)
    purchase_rows={}
    for row in expenses:
        key=("purchase",row.purchase_id) if row.purchase_id else ("legacy",row.id)
        group=purchase_rows.setdefault(key,{"ID":row.purchase_id or row.id,"Date":(row.purchase.date if row.purchase_id else row.date).isoformat(),"Category":row.purchase.category if row.purchase_id else row.category,"Responsible":row.purchase.responsible if row.purchase_id else row.responsible,"Notes":row.purchase.notes if row.purchase_id else expense_notes(row.notes),"Lines":[],"Amount":0,"Quantity":0})
        quantity=expense_quantity(row.notes)
        group["Lines"].append({"ID":row.id,"Concept":row.concept,"Quantity":quantity,"Unit":expense_unit(row.cents,row.notes),"AmountMx":row.cents/100,"Notes":expense_notes(row.notes)})
        group["Amount"]+=row.cents
        group["Quantity"]+=quantity
    days={}
    for group in purchase_rows.values():
        group["AmountMx"]=group["Amount"]/100
        group["ProductCount"]=len(group["Lines"])
        day=days.setdefault(group["Date"],{"Date":group["Date"],"Purchases":[],"Amount":0,"PurchaseCount":0,"ProductCount":0,"Quantity":0})
        day["Purchases"].append(group)
        day["Amount"]+=group["Amount"]
        day["PurchaseCount"]+=1
        day["ProductCount"]+=len(group["Lines"])
        day["Quantity"]+=group["Quantity"]
    expense_days=list(days.values())
    for day in expense_days: day["AmountMx"]=day["Amount"]/100
    today=timezone.localdate().isoformat()
    ctx=base_context(request, Today=today, SelectedDate=selected_date, CanEdit=current_role(request.user) in (ADMIN,"finanzas"), Items=[{"ID":x.id,"Date":x.date.isoformat(),"Concept":x.concept,"Amount":x.cents,"AmountMx":x.cents/100,"Quantity":expense_quantity(x.notes),"Unit":expense_unit(x.cents,x.notes),"Origin":x.origin,"Responsible":x.responsible,"Notes":expense_notes(x.notes)} for x in incomes], ExpenseDays=expense_days, Total=sum(x.cents for x in incomes), ExpenseTotal=sum(x.cents for x in expenses), Message=request.GET.get("mensaje",""))
    ctx["TotalMx"] = ctx["Total"] / 100
    ctx["ExpenseTotalMx"] = ctx["ExpenseTotal"] / 100
    return render(request,"pages/finance.html",ctx)

def expense_quantity(notes):
    match=re.search(r"Cantidad: ([0-9]+);",notes or "")
    return int(match.group(1)) if match else 1

def expense_unit(cents,notes):
    match=re.search(r"precio unitario: ([0-9]+(?:\.[0-9]+)?);",notes or "")
    return match.group(1) if match else str(Decimal(cents)/100)

def expense_notes(notes):
    match=re.search(r"Notas: (.*)$",notes or "")
    return match.group(1) if match else notes

def _money_form(request, expense=False):
    prefix="egreso" if expense else "ingreso"; item=request.POST
    if not item.get("id") and item.getlist("productos_nombre"):
        return _multi_money_form(request, expense)
    form_data=item
    if not expense and item.get("id") and item.get("cantidad") and item.get("precio_unitario"):
        try:
            quantity=Decimal(item["cantidad"]);unit=Decimal(item["precio_unitario"])
            form_data=item.copy();form_data["monto"]=str(quantity*unit)
        except InvalidOperation:return form_feedback("/finanzas","Revisa la cantidad y el precio unitario del ingreso.")
    form=(ExpenseForm if expense else IncomeForm)(form_data)
    if not form.is_valid():
        return form_feedback("/finanzas","Revisa los datos de "+prefix+" e inténtalo de nuevo.")
    data=form.cleaned_data
    concept=data["concepto"]; source=data["categoria" if expense else "origen"]
    responsible=data["responsable"]; notes=data["notas"]
    try:
        day=data["fecha"]; quantity=Decimal(data["cantidad"] if expense else (item.get("cantidad") or 1)); unit=data["precio_unitario"] if expense else (Decimal(item.get("precio_unitario")) if item.get("precio_unitario") else data["monto"])
        if quantity <= 0 or quantity > 1000000 or quantity != quantity.to_integral_value() or unit <= 0 or unit > Decimal("1000000000"): raise ValueError()
        amount=quantity*unit; cents=int(amount*100+Decimal("0.5"))
        if not concept or len(concept)>200 or len(source)>160 or len(responsible)>160 or len(notes)>1000 or amount>Decimal("1000000000") or Decimal(cents)/100 != amount: raise ValueError()
    except (ValueError,InvalidOperation): return form_feedback("/finanzas","Revisa los datos de "+prefix+" e inténtalo de nuevo.")
    cls=Expense if expense else Income; fields={"concept":concept,"cents":cents,"date":day,"responsible":responsible,"notes":notes,"registered_by":request.user}
    fields["category" if expense else "origin"]=source
    if expense or item.get("cantidad"):
        fields["notes"]=("Cantidad: %s; precio unitario: %s; Notas: %s"%(quantity,unit,notes)).strip()
    item_id=request.POST.get("id")
    if item_id:
        try:record=cls.objects.get(pk=parse_id(item_id))
        except (ValueError,cls.DoesNotExist):return form_feedback("/finanzas","El registro que intentas editar ya no existe.")
        for key,value in fields.items():
            if key!="purchase":setattr(record,key,value)
        if expense and record.purchase_id:
            record.purchase.date=day;record.purchase.category=source;record.purchase.responsible=responsible;record.purchase.notes=notes;record.purchase.save()
            Expense.objects.filter(purchase_id=record.purchase_id).update(date=day,category=source,responsible=responsible)
        record.save()
    elif expense:
        with transaction.atomic():
            fields["purchase"]=Purchase.objects.create(date=day,category=source,responsible=responsible,notes=notes,registered_by=request.user)
            cls.objects.create(**fields)
    else:cls.objects.create(**fields)
    return see_other("/finanzas?mensaje="+ ("Egreso" if expense else "Ingreso") + "%20registrado")

def _multi_money_form(request, expense):
    """Guarda todos los productos de una compra bajo un mismo registro."""
    f=request.POST; names=f.getlist("productos_nombre"); quantities=f.getlist("productos_cantidad"); prices=f.getlist("productos_precio")
    source=f.get("categoria" if expense else "origen", "").strip(); responsible=f.get("responsable", "").strip(); notes=f.get("notas", "").strip()
    try:
        day=parse_date(f.get("fecha", "")) if f.get("fecha") else timezone.localdate()
        if len(source)>160 or len(responsible)>160 or len(notes)>1000 or not (len(names)==len(quantities)==len(prices)) or not names:
            raise ValueError()
        rows=[]; total=Decimal("0")
        for name, count, price in zip(names, quantities, prices):
            name=name.strip()
            if not name and not count and not price: continue
            if not name or len(name)>200: raise ValueError()
            qty=Decimal(count); unit=Decimal(price)
            if qty<1 or qty>1000000 or qty!=qty.to_integral_value() or unit<=0 or unit>Decimal("1000000000") or unit.as_tuple().exponent < -2:
                raise ValueError()
            amount=qty*unit
            if amount>Decimal("1000000000"): raise ValueError()
            cents=int(amount*100); total+=amount
            row_notes="Cantidad: %s; precio unitario: %s; Notas: %s"%(qty,unit,notes)
            fields={"concept":name,"cents":cents,"date":day,"responsible":responsible,"notes":row_notes,"registered_by":request.user}
            fields["category" if expense else "origin"]=source
            rows.append(fields)
        if not rows or total>Decimal("1000000000"): raise ValueError()
        with transaction.atomic():
            if expense:
                purchase=Purchase.objects.create(date=day,category=source,responsible=responsible,notes=notes,registered_by=request.user)
                for row in rows: row["purchase"]=purchase
            (Expense if expense else Income).objects.bulk_create([(Expense if expense else Income)(**row) for row in rows])
    except (ValueError, TypeError, InvalidOperation):
        return form_feedback("/finanzas","Revisa los productos, cantidades y precios.")
    return see_other("/finanzas?mensaje="+("Compra" if expense else "Venta o ingreso")+"%20registrado")

def income_create(request):
    gate=allowed(request,"finanzas")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo Finanzas y administración pueden registrar movimientos.","/finanzas")
    if request.method!="POST":return HttpResponse("Método no permitido.",status=405)
    return _money_form(request)

def income_edit(request):
    gate=allowed(request,"*")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo administración y Finanzas pueden editar registros.","/finanzas")
    return _money_form(request) if request.method=="POST" else error_page(405,"Método no disponible","Usa el formulario.","/finanzas")

def income_delete(request):
    return finance_delete(request,Income)

def expense_edit(request):
    gate=allowed(request,"*")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo administración y Finanzas pueden editar registros.","/finanzas")
    return _money_form(request,True) if request.method=="POST" else error_page(405,"Método no disponible","Usa el formulario.","/finanzas")

def expense_delete(request):
    if request.method == "POST" and request.POST.getlist("purchase_ids"):
        gate=allowed(request,"*")
        if gate:return gate
        if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo administración y Finanzas pueden eliminar registros.","/finanzas")
        try: ids=[parse_id(value) for value in request.POST.getlist("purchase_ids")]
        except ValueError:return form_feedback("/finanzas","La selección contiene una compra no válida.")
        Purchase.objects.filter(pk__in=ids).delete()
        return see_other("/finanzas?mensaje=Compra%20eliminada")
    purchase_id=None
    if request.method=="POST" and request.POST.get("id"):
        try: purchase_id=Expense.objects.filter(pk=parse_id(request.POST["id"])).values_list("purchase_id",flat=True).first()
        except ValueError: pass
    response=finance_delete(request,Expense)
    if purchase_id and response.status_code==303 and not Expense.objects.filter(purchase_id=purchase_id).exists():
        Purchase.objects.filter(pk=purchase_id).delete()
    return response

def finance_delete(request,model):
    gate=allowed(request,"*")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo administración y Finanzas pueden eliminar registros.","/finanzas")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario.","/finanzas")
    ids=request.POST.getlist("ids") or [request.POST.get("id","")]
    if ids==[""]:return form_feedback("/finanzas","Selecciona al menos un movimiento para eliminar.")
    try:ids=[parse_id(value) for value in ids]
    except ValueError:return form_feedback("/finanzas","La selección contiene un movimiento no válido.")
    model.objects.filter(pk__in=ids).delete()
    return see_other("/finanzas?mensaje=Registro%20eliminado")
def expense_create(request):
    gate=allowed(request,"finanzas")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"finanzas"):return error_page(403,"Acceso restringido","Solo Finanzas y administración pueden registrar movimientos.","/finanzas")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario para registrar el egreso.","/finanzas")
    return _money_form(request,True)

def export(request):
    gate=allowed(request,"finanzas")
    if gate:return gate
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:return HttpResponse("No fue posible generar el reporte.",status=500)
    wb=Workbook(); ws=wb.active; ws.title="Compras"; ws.append(["Fecha","Cantidad","Concepto","Precio unitario (MXN)","Total compra (MXN)","Total del día (MXN)","Categoría","Responsable","Notas","Registrado el"])
    daily={}
    for row in Expense.objects.order_by("date","id"):
        try:
            quantity=Decimal(row.notes.split("Cantidad: ",1)[1].split(";",1)[0])
            unit=Decimal(row.notes.split("precio unitario: ",1)[1].split(";",1)[0])
            notes=row.notes.split("Notas: ",1)[1] if "Notas: " in row.notes else ""
        except (IndexError,InvalidOperation): quantity,unit,notes=Decimal(1),Decimal(row.cents)/100,row.notes
        daily[row.date]=daily.get(row.date,0)+row.cents
        ws.append([row.date.isoformat(),int(quantity),row.concept,float(unit),row.cents/100,daily[row.date]/100,row.category,row.responsible,notes,row.created_at.strftime("%Y-%m-%d %H:%M")])
    ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
    for cell in ws[1]: cell.font=Font(bold=True,color="FFFFFFFF"); cell.fill=PatternFill("solid",fgColor="14332A")
    for cell in ws["C"][1:]: cell.data_type="s"
    for i,width in enumerate([14,12,32,22,22,22,24,24,48,20],1):ws.column_dimensions[get_column_letter(i)].width=width
    for col in ("D","E","F"):
        for cell in ws[col][1:]:cell.number_format='$#,##0.00'
    income=wb.create_sheet("Ingresos"); income.append(["Fecha","Cantidad","Concepto","Monto total (MXN)","Precio unitario (MXN)","Origen","Responsable","Notas","Registrado el"])
    for row in Income.objects.order_by("-date","-id"):
        income.append([row.date.isoformat(),expense_quantity(row.notes),row.concept,row.cents/100, row.cents/100/expense_quantity(row.notes),row.origin,row.responsible,expense_notes(row.notes),row.created_at.strftime("%Y-%m-%d %H:%M")])
    income.freeze_panes="A2";income.auto_filter.ref=income.dimensions
    for cell in income[1]:cell.font=Font(bold=True,color="FFFFFFFF");cell.fill=PatternFill("solid",fgColor="14332A")
    for col,width in enumerate([14,12,32,17,22,24,24,48,20],1):income.column_dimensions[get_column_letter(col)].width=width
    for col in ("D","E"):
        for cell in income[col][1:]:cell.number_format='$#,##0.00'
    out=io.BytesIO();wb.save(out); response=HttpResponse(out.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");response["Content-Disposition"]='attachment; filename="reporte-finanzas.xlsx"';return response

def receipts(request):
    gate=allowed(request,"finanzas")
    if gate:return gate
    return render(request,"pages/receipts.html",base_context(request,Title="Comprobantes"))
def projects(request):
    gate=allowed(request,"*")
    if gate:return gate
    if request.method!="GET":return HttpResponse("Método no permitido.",status=405)
    selected_date=request.GET.get("fecha","").strip()
    try: selected_day=parse_date(selected_date) if selected_date else None
    except ValueError: selected_day=None; selected_date=""
    deadlines=ProjectDeadline.objects.order_by("due_date","title")
    notes=ProjectNote.objects.order_by("-created_at")
    if selected_day:
        deadlines=deadlines.filter(due_date=selected_day)
        notes=notes.filter(created_at__date=selected_day)
    deadlines=list(deadlines); notes=list(notes)
    deadline_groups={}; note_groups={}
    for item in deadlines:
        group=deadline_groups.setdefault(item.due_date,{"Date":item.due_date,"Items":[]})
        group["Items"].append(item)
    for item in notes:
        day=timezone.localtime(item.created_at).date()
        group=note_groups.setdefault(day,{"Date":day,"Items":[]})
        group["Items"].append(item)
    return render(request,"pages/projects.html",base_context(request,Title="Proyectos",CanEdit=current_role(request.user) in (ADMIN,"proyectos"),SelectedDate=selected_date,Deadlines=deadlines,DeadlineDays=list(deadline_groups.values()),Inventory=ProjectInventory.objects.order_by("item"),Notes=notes,NoteDays=list(note_groups.values())))

def project_save(request):
    gate=allowed(request,"*")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"proyectos"):return error_page(403,"Acceso restringido","Solo Proyectos y administración pueden editar esta sección.","/proyectos")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario de Proyectos.","/proyectos")
    f=request.POST; kind=f.get("tipo")
    try:
        object_id=f.get("id","")
        if kind=="deadline":
            form=ProjectDeadlineForm({"title":f.get("titulo",""),"due_date":f.get("fecha",""),"notes":f.get("notas","")})
            if not form.is_valid(): raise ValueError()
            values=form.cleaned_data
            if object_id:
                record=ProjectDeadline.objects.get(pk=parse_id(object_id))
                for key,value in values.items():setattr(record,key,value)
                record.save()
            else:ProjectDeadline.objects.create(**values,created_by=request.user)
        elif kind=="inventory":
            form=ProjectInventoryForm({"item":f.get("articulo",""),"quantity":f.get("cantidad",""),"notes":f.get("notas","")})
            if not form.is_valid(): raise ValueError()
            values=form.cleaned_data
            if object_id:
                record=ProjectInventory.objects.get(pk=parse_id(object_id))
                for key,value in values.items():setattr(record,key,value)
                record.save()
            else:ProjectInventory.objects.create(**values)
        elif kind=="note":
            form=ProjectNoteForm({"title":f.get("titulo",""),"body":f.get("contenido","")})
            if not form.is_valid(): raise ValueError()
            values=form.cleaned_data
            if object_id:
                record=ProjectNote.objects.get(pk=parse_id(object_id))
                for key,value in values.items():setattr(record,key,value)
                record.save()
            else:ProjectNote.objects.create(**values,created_by=request.user)
        else:raise ValueError()
    except (ValueError,TypeError,ProjectDeadline.DoesNotExist,ProjectInventory.DoesNotExist,ProjectNote.DoesNotExist):return form_feedback("/proyectos","Revisa los campos o confirma que el elemento todavía exista.")
    return see_other("/proyectos")

def project_delete(request):
    gate=allowed(request,"*")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"proyectos"):return error_page(403,"Acceso restringido","Solo Proyectos y administración pueden eliminar información.","/proyectos")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario.","/proyectos")
    models={"deadline":ProjectDeadline,"inventory":ProjectInventory,"note":ProjectNote}
    try:
        ids=request.POST.getlist("ids") or [request.POST.get("id","")]
        if ids==[""]:return form_feedback("/proyectos","Selecciona al menos un elemento para eliminar.")
        ids=[parse_id(value) for value in ids]
        models[request.POST.get("tipo")].objects.filter(pk__in=ids).delete()
    except (KeyError,ValueError):return form_feedback("/proyectos","La selección contiene un elemento no válido.")
    return see_other("/proyectos")
def project_phases(request):
    gate=allowed(request,"*")
    if current_role(request.user) not in (ADMIN,"proyectos","presidente","vicepresidente"):return gate or error_page(403,"Acceso restringido","No tienes acceso a esta sección.","/proyectos")
    return gate or render(request,"pages/project_phases.html",base_context(request,Title="Fases del proyecto"))
def assets(request):
    gate=allowed(request,"*")
    if gate:return gate
    if request.method!="GET":return error_page(405,"Método no disponible","Esta página solo permite consultas.","/")
    purge_expired_assets()
    data=[]
    query=request.GET.get("q","").strip()[:200]
    files=SharedAsset.objects.order_by("-created_at")
    if query:files=files.filter(name__icontains=query)
    for item in files:
        data.append(asset_context(item))
    trash=[]
    if current_role(request.user)==ADMIN:
        for item in SharedAssetTrash.objects.order_by("-deleted_at"):
            trash.append({**asset_context(item),"ID":item.id,"Deleted":item.deleted_at.strftime("%Y-%m-%d %H:%M"),"DaysLeft":max(0,15-(timezone.now()-item.deleted_at).days)})
    return render(request,"pages/assets.html",base_context(request,Title="Drive",Items=data,Trash=trash,Query=query,CanUpload=current_role(request.user) in (ADMIN,"difusion"),CanDelete=current_role(request.user)==ADMIN,CanManage=current_role(request.user) in (ADMIN,"difusion"),Message=request.GET.get("mensaje","")))

def asset_context(item):
    return {"ID":item.id,"Name":item.name,"Extension":Path(item.name).suffix.lstrip("."),"Type":item.content_type,"Uploaded":item.uploaded_by.username if item.uploaded_by else "—","Created":item.created_at.strftime("%Y-%m-%d %H:%M") if hasattr(item,"created_at") else item.original_created_at.strftime("%Y-%m-%d %H:%M"),"Size":format_size(item.bytes),"Previewable":True}

def purge_expired_assets():
    """Retira de forma irreversible archivos cuya retención superó 15 días."""
    cutoff=timezone.now()-timezone.timedelta(days=15)
    root=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")))
    expired=SharedAssetTrash.objects.filter(deleted_at__lte=cutoff)
    for item in expired.iterator():
        (root/Path(item.file).name).unlink(missing_ok=True)
        item.delete()

def move_asset_to_trash(item, user):
    """Conserva el archivo y sus metadatos antes de retirar su registro activo."""
    SharedAssetTrash.objects.create(asset_id=item.id,name=item.name,file=item.file,content_type=item.content_type,bytes=item.bytes,uploaded_by=item.uploaded_by,original_created_at=item.created_at,deleted_by=user)
    item.delete()
def asset_upload(request):
    gate=allowed(request,"gestores_assets")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"difusion"):return error_page(403,"Acceso restringido","Solo Difusión y administración pueden subir archivos.","/drive")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario para subir un archivo.","/assets")
    files=request.FILES.getlist("archivos") or request.FILES.getlist("archivo")
    if not files:return error_page(400,"Selecciona archivos","Elige uno o más archivos de hasta 20 MB cada uno.","/assets")
    if len(files)>20:return error_page(400,"Demasiados archivos","Puedes subir hasta 20 archivos a la vez.","/assets")
    target=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")));target.mkdir(parents=True,exist_ok=True)
    created_paths=[]
    try:
        with transaction.atomic():
            for file in files:
                if file.size<=0 or file.size>20*1024*1024:raise ValueError("size")
                name=Path(file.name.strip()).name
                if name in (".","") or len(name.encode())>255:raise ValueError("name")
                stored=uuid.uuid4().hex+Path(name).suffix.lower();path=target/stored;sample=bytearray()
                with path.open("xb") as out:
                    size=0
                    for chunk in file.chunks():
                        size+=len(chunk);out.write(chunk)
                        if len(sample)<512:sample.extend(chunk[:512-len(sample)])
                created_paths.append(path)
                if size!=file.size or size>20*1024*1024:raise ValueError("size")
                content_type=detect_content_type(bytes(sample),Path(name).suffix)
                SharedAsset.objects.create(name=name,file=stored,content_type=content_type,bytes=size,uploaded_by=request.user)
    except ValueError as error:
        for path in created_paths:path.unlink(missing_ok=True)
        message="El nombre de uno de los archivos no es válido." if str(error)=="name" else "Cada archivo debe pesar entre 1 byte y 20 MB."
        return error_page(400,"Revisa los archivos",message,"/drive")
    except Exception:
        for path in created_paths:path.unlink(missing_ok=True)
        return error_page(500,"No se pudieron guardar los archivos","No se guardaron cambios; inténtalo de nuevo.","/drive")
    return see_other("/drive?mensaje=Archivos%20subidos")

def asset_replace(request):
    gate=allowed(request,"gestores_assets")
    if gate:return gate
    if current_role(request.user) not in (ADMIN,"difusion"):return error_page(403,"Acceso restringido","Solo Difusión y administración pueden reemplazar archivos.","/drive")
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario de reemplazo.","/drive")
    try:item=SharedAsset.objects.get(pk=parse_id(request.POST.get("id","")))
    except (ValueError,SharedAsset.DoesNotExist):return error_page(404,"Archivo no encontrado","El archivo ya no está disponible.","/drive")
    replacement=request.FILES.get("archivo")
    if not replacement or replacement.size<=0 or replacement.size>20*1024*1024:return error_page(400,"Archivo no válido","El reemplazo debe pesar entre 1 byte y 20 MB.","/drive")
    name=Path(replacement.name.strip()).name
    if name in (".","") or len(name.encode())>255:return error_page(400,"Nombre no válido","Renombra el archivo e inténtalo de nuevo.","/drive")
    target=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")));stored=uuid.uuid4().hex+Path(name).suffix.lower();path=target/stored;sample=bytearray()
    try:
        with path.open("xb") as out:
            size=0
            for chunk in replacement.chunks():
                size+=len(chunk);out.write(chunk)
                if len(sample)<512:sample.extend(chunk[:512-len(sample)])
        if size!=replacement.size or size>20*1024*1024:raise ValueError()
        with transaction.atomic():
            move_asset_to_trash(item,request.user)
            SharedAsset.objects.create(name=name,file=stored,content_type=detect_content_type(bytes(sample),Path(name).suffix),bytes=size,uploaded_by=request.user)
    except Exception:
        path.unlink(missing_ok=True)
        return error_page(500,"No se pudo reemplazar","El archivo anterior se conserva en Drive.","/drive")
    return see_other("/drive?mensaje=Archivo%20reemplazado")

def asset_preview(request):
    gate=allowed(request,"*")
    if gate:return gate
    try:item=SharedAsset.objects.get(pk=parse_id(request.GET.get("id","")))
    except (ValueError,SharedAsset.DoesNotExist):return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/drive")
    path=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")))/Path(item.file).name
    if not path.is_file():return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/drive")
    ext=Path(item.name).suffix.lower()
    ctx=base_context(request,Title="Vista previa",Asset=asset_context(item),PreviewFile="/assets/preview/file?id=%s"%item.id,PreviewKind="binary",BinaryPreview="")
    if item.content_type.startswith("image/") or item.content_type=="application/pdf":ctx["PreviewKind"]="embed"
    elif item.content_type.startswith("audio/"):ctx["PreviewKind"]="audio"
    elif item.content_type.startswith("video/"):ctx["PreviewKind"]="video"
    elif ext in (".docx",".pptx",".xlsx"):
        try:
            with zipfile.ZipFile(path) as archive:
                if ext==".docx":ctx.update(PreviewKind="document",PreviewText=docx_preview(archive))
                elif ext==".pptx":ctx.update(PreviewKind="slides",PreviewSlides=pptx_preview(archive))
                else:ctx.update(PreviewKind="spreadsheet",PreviewSheets=xlsx_preview(archive))
        except (zipfile.BadZipFile,ET.ParseError,KeyError,ValueError):ctx["PreviewKind"]="binary"
    elif ext in (".odt",".odp",".ods"):
        try:
            with zipfile.ZipFile(path) as archive:
                root=zip_xml(archive,"content.xml")
                if ext==".odt":ctx.update(PreviewKind="document",PreviewText=["".join(node.itertext()).strip() for node in root.iter() if node.tag.endswith(("}p","}h")) and "".join(node.itertext()).strip()][:1000])
                elif ext==".odp":ctx.update(PreviewKind="slides",PreviewSlides=[{"Number":i,"Text":" ".join(node.itertext())} for i,node in enumerate((node for node in root.iter() if node.tag.endswith("}page")),1)])
                else:ctx.update(PreviewKind="spreadsheet",PreviewSheets=[[" ".join(cell.itertext()) for cell in row if cell.tag.endswith("}table-cell")] for row in root.iter() if row.tag.endswith("}table-row")][:300])
        except (zipfile.BadZipFile,ET.ParseError,KeyError,ValueError):ctx["PreviewKind"]="binary"
    elif ext in (".zip",".cbz"):
        try:
            with zipfile.ZipFile(path) as archive:ctx.update(PreviewKind="archive",ArchiveFiles=archive.namelist()[:500])
        except zipfile.BadZipFile:ctx["PreviewKind"]="binary"
    elif item.content_type.startswith("text/") or ext in (".json",".xml",".md",".py",".js",".css",".html",".csv",".yml",".yaml",".toml",".ini",".log",".sql",".sh"):
        try:
            if item.bytes>2*1024*1024:raise ValueError()
            ctx.update(PreviewKind="text",PreviewText=path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError,ValueError):ctx["PreviewKind"]="binary"
    if ctx["PreviewKind"]=="binary":
        with path.open("rb") as source: sample=source.read(256)
        ctx["BinaryPreview"]=" ".join("%02X"%byte for byte in sample)
    return render(request,"pages/asset_preview.html",ctx)

def asset_preview_file(request):
    gate=allowed(request,"*")
    if gate:return gate
    try:item=SharedAsset.objects.get(pk=parse_id(request.GET.get("id","")))
    except (ValueError,SharedAsset.DoesNotExist):return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/drive")
    path=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")))/Path(item.file).name
    if not path.is_file():return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/drive")
    response=FileResponse(path.open("rb"),content_type=item.content_type);response["X-Content-Type-Options"]="nosniff";response["Content-Security-Policy"]="default-src 'none'; sandbox"
    return response

def zip_xml(archive,name,limit=512*1024):
    info=archive.getinfo(name)
    if info.file_size>limit:raise ValueError("preview size limit")
    return ET.fromstring(archive.read(name))

def docx_preview(archive):
    root=zip_xml(archive,"word/document.xml")
    ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return ["".join(node.itertext()).strip() for node in root.findall(".//w:p",ns) if "".join(node.itertext()).strip()][:1000]

def pptx_preview(archive):
    names=sorted((name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",name)),key=lambda name:int(re.search(r"slide(\d+)",name).group(1)))
    slides=[]
    for index,name in enumerate(names[:50],1):
        root=zip_xml(archive,name);texts=[node.text or "" for node in root.iter() if node.tag.endswith("}t")]
        slides.append({"Number":index,"Text":" ".join(texts)})
    return slides

def xlsx_preview(archive):
    shared=[]
    if "xl/sharedStrings.xml" in archive.namelist():
        root=zip_xml(archive,"xl/sharedStrings.xml");shared=["".join(node.itertext()) for node in root]
    rows=[]
    names=sorted((name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",name)),key=lambda name:int(re.search(r"sheet(\d+)",name).group(1)))
    for name in names[:5]:
        root=zip_xml(archive,name)
        for row in root.iter():
            if not row.tag.endswith("}row"):continue
            cells=[]
            for cell in row:
                if not cell.tag.endswith("}c"):continue
                if cell.attrib.get("t")=="inlineStr":value="".join(cell.itertext())
                else:value=next((child.text or "" for child in cell if child.tag.endswith("}v")),"")
                if cell.attrib.get("t")=="s" and value.isdigit() and int(value)<len(shared):value=shared[int(value)]
                cells.append(value)
            rows.append(cells)
            if len(rows)>=300: return rows
    return rows

def asset_restore(request):
    gate=allowed(request,ADMIN)
    if gate:return gate
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario.","/drive")
    try:item=SharedAssetTrash.objects.get(pk=parse_id(request.POST.get("id","")))
    except (ValueError,SharedAssetTrash.DoesNotExist):return error_page(404,"Elemento no encontrado","La papelera pudo haber vencido.","/drive")
    with transaction.atomic():
        values={"name":item.name,"file":item.file,"content_type":item.content_type,"bytes":item.bytes,"uploaded_by":item.uploaded_by,"created_at":item.original_created_at}
        if not SharedAsset.objects.filter(pk=item.asset_id).exists():values["id"]=item.asset_id
        SharedAsset.objects.create(**values)
        item.delete()
    return see_other("/drive?mensaje=Archivo%20restaurado")

def detect_content_type(sample, extension):
    if extension and mimetypes.guess_type("file"+extension)[0]:return mimetypes.guess_type("file"+extension)[0]
    signatures=((b"\x89PNG\r\n\x1a\n","image/png"),(b"\xff\xd8\xff","image/jpeg"),(b"GIF87a","image/gif"),(b"GIF89a","image/gif"),(b"%PDF-","application/pdf"),(b"PK\x03\x04","application/zip"),(b"\x1f\x8b\x08","application/gzip"))
    for signature,content_type in signatures:
        if sample.startswith(signature):return content_type
    if sample.startswith((b"<!DOCTYPE html",b"<html",b"<HTML")):return "text/html; charset=utf-8"
    try:sample.decode("utf-8");return "text/plain; charset=utf-8"
    except UnicodeDecodeError:return "application/octet-stream"
def asset_download(request):
    gate=allowed(request,"*")
    if gate:return gate
    try:item=SharedAsset.objects.get(pk=parse_id(request.GET.get("id","")))
    except (ValueError,SharedAsset.DoesNotExist):return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/assets")
    path=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")))/Path(item.file).name
    if not path.is_file():return error_page(404,"Archivo no encontrado","El recurso solicitado no está disponible.","/assets")
    response=FileResponse(path.open("rb"),as_attachment=True,filename=item.name,content_type=item.content_type);response["X-Content-Type-Options"]="nosniff";return response

def asset_delete(request):
    gate=allowed(request,ADMIN)
    if gate:return gate
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario.","/drive")
    ids=request.POST.getlist("ids") or [request.POST.get("id","")]
    if ids==[""]:return form_feedback("/drive","Selecciona al menos un archivo para eliminar.")
    try:ids=[parse_id(value) for value in ids]
    except ValueError:return form_feedback("/drive","La selección contiene un archivo no válido.")
    target=Path(os.getenv("MEDIA_ROOT",str(Path(__file__).resolve().parent.parent/"data"/"assets")))
    for item in SharedAsset.objects.filter(pk__in=ids):
        path=target/Path(item.file).name
        item.delete();path.unlink(missing_ok=True)
    return see_other("/drive?mensaje=Archivo%20eliminado")

def format_size(size):
    if size<1024:return "%d B"%size
    if size<1024*1024:return "%.0f KB"%(size/1024)
    return "%.1f MB"%(size/(1024*1024))

def users(request):
    gate=allowed(request,"administrador")
    if gate:return gate
    Role.objects.get_or_create(name="difusion",defaults={"description":"Gestión de difusión y archivos compartidos"})
    if request.method=="GET":
        accounts=[{"ID":u.id,"Username":u.username,"Role":"" if u.role_name=="servicio_social" else u.role_name,"Approved":u.approved,"Active":u.is_active} for u in User.objects.prefetch_related("roles").order_by("approved","id")]
        roles_list=[{"ID":r.id,"Name":r.name} for r in Role.objects.filter(active=True).exclude(name="servicio_social").order_by("id")]
        return render(request,"pages/users.html",base_context(request,Title="Usuarios",Accounts=accounts,Roles=roles_list))
    if request.method!="POST":return error_page(405,"Método no disponible","Usa el formulario de cuentas.","/usuarios")
    f=request.POST
    if f.get("accion")=="crear":
        try:
            username=f.get("usuario","").strip();password=f.get("contrasena","");role=Role.objects.get(name=f.get("rol"),active=True);approved=f.get("acceso")=="on"
            if not username or len(username.encode())>100 or not valid_password_for_role(password,role):raise ValueError()
            if User.objects.filter(username=username).exists():return action_error(409,"Ese usuario ya existe","Elige otro nombre de usuario.","/usuarios")
            account=User.objects.create_user(username,password,is_active=approved,approved=approved)
            if approved:account.roles.add(role)
            return see_other("/usuarios")
        except (ValueError,Role.DoesNotExist,IntegrityError):return form_feedback("/usuarios","Revisa el usuario, la contraseña o el NIP correspondiente al rol.")
    try:
        account=User.objects.get(pk=parse_id(f["id"]))
        if f.get("accion")=="eliminar":
            if account.pk==request.user.pk:return action_error(403,"No puedes eliminar tu propia cuenta.","Pide a otra persona administradora que realice este cambio.","/usuarios")
            account.delete();return see_other("/usuarios")
        if f.get("accion")=="rechazar":
            account.approved=False;account.is_active=False;account.save(update_fields=["approved","is_active"]);account.roles.clear();invalidate_user_sessions(account.pk)
            return see_other("/usuarios")
        username=f.get("usuario","").strip();role_name=f.get("rol","");password=f.get("contrasena","");approved=f.get("acceso")=="on"
        if not username or len(username.encode())>100:raise ValueError()
        if approved and not role_name:raise ValueError()
        role=Role.objects.get(name=role_name,active=True) if role_name else None
        if approved and not role:raise ValueError()
        if password and not valid_password_for_role(password,role):raise ValueError()
        if approved and role and role.name==ADMIN and not password and account.role_name!=ADMIN:
            return form_feedback("/usuarios","Al asignar Administración debes definir una contraseña de al menos 10 caracteres.")
        if User.objects.filter(username=username).exclude(pk=account.pk).exists():return action_error(409,"Ese usuario ya existe","Elige otro nombre de usuario.","/usuarios")
        account.username=username;account.is_active=approved;account.approved=approved
        if password:account.set_password(password)
        account.save();account.roles.clear()
        if approved and role:account.roles.add(role)
        keep_current_session=account.pk==request.user.pk and approved and role and role.name==ADMIN
        if keep_current_session and password:
            # Actualiza el hash de autenticación de la sesión que está cambiando su propio NIP.
            update_session_auth_hash(request,account)
        invalidate_user_sessions(account.pk,request.session.session_key if keep_current_session else None)
        return see_other("/usuarios")
    except User.DoesNotExist:return error_page(404,"Cuenta no encontrada","La cuenta pudo haber sido eliminada.","/usuarios")
    except (ValueError,Role.DoesNotExist,IntegrityError):return form_feedback("/usuarios","Revisa el usuario, el rol y la contraseña o el NIP correspondiente.")

def roles(request):
    gate=allowed(request,"administrador")
    if gate:return gate
    return render(request,"pages/section.html",base_context(request,Title="Roles",Rows=[{"Nombre":r.name,"Name":r.name} for r in Role.objects.filter(active=True).exclude(name="servicio_social").order_by("id")]))

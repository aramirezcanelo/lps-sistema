from django.test import Client, TestCase
import io
import bcrypt
from .models import User, Role, Income, Expense, ProjectNote, ProjectInventory

class WebContractTests(TestCase):
    def setUp(self):
        import os
        import tempfile
        from unittest.mock import patch

        media = tempfile.TemporaryDirectory()
        media_env = patch.dict(os.environ, {"MEDIA_ROOT": media.name})
        media_env.start()
        self.addCleanup(media_env.stop)
        self.addCleanup(media.cleanup)

    @classmethod
    def setUpTestData(cls):
        cls.admin_role = Role.objects.get(name="administrador")
        cls.finance_role = Role.objects.get(name="finanzas")
        cls.admin = User.objects.create_user("admin", "correct horse battery")
        cls.admin.roles.add(cls.admin_role)
        cls.other = User.objects.create_user("other", "other account")
        cls.other.roles.add(Role.objects.get(name="proyectos"))
        cls.finance = User.objects.create_user("finance", "correct horse battery")
        cls.finance.roles.add(cls.finance_role)
        cls.president = User.objects.create_user("president", "2468")
        cls.president.roles.add(Role.objects.get(name="presidente"))
        cls.vice = User.objects.create_user("vice", "1357")
        cls.vice.roles.add(Role.objects.get(name="vicepresidente"))

    def test_health_check_returns_plain_success(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
        self.assertTrue(response["Content-Type"].startswith("text/plain"))

    def test_presidency_and_hr_sections_are_removed_but_roles_remain(self):
        self.assertTrue(Role.objects.filter(name__in=("presidente", "vicepresidente", "recursos_humanos")).exists())
        for path in ("/presidencia", "/recursos-humanos"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get("/")
        self.assertNotContains(response, "/presidencia")
        self.assertNotContains(response, "/recursos-humanos")
        self.assertContains(self.client.get("/roles"), "presidente")
        self.assertContains(self.client.get("/roles"), "recursos_humanos")

    def test_django_admin_is_restricted_to_the_administrator_role(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.client.force_login(self.finance)
        denied = self.client.get("/admin/")
        self.assertEqual(denied.status_code, 302)
        self.assertTrue(denied.url.startswith("/admin/login/"))

    def test_login_success_uses_django_session_and_303(self):
        response = self.client.post("/login", {"usuario": "admin", "contrasena": "correct horse battery", "next": "/"})
        self.assertEqual(response.status_code, 303)
        self.assertTrue(self.client.session.session_key)
        self.assertIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(response.cookies["sessionid"]["samesite"], "Lax")
        self.assertEqual(self.client.get("/proyectos").status_code, 200)

    def test_login_failure_redirects_with_original_message(self):
        response = self.client.post("/login", {"usuario": "admin", "contrasena": "bad"})
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.url)

    def test_role_credentials_enforce_admin_password_and_leadership_nip(self):
        self.assertEqual(self.client.post("/login", {"usuario":"admin", "contrasena":"1234"}).status_code, 303)
        self.assertIn("error=", self.client.post("/login", {"usuario":"admin", "contrasena":"1234"}).url)
        self.assertEqual(self.client.post("/login", {"usuario":"president", "contrasena":"2468"}).status_code,303)
        self.client.post("/logout")
        self.assertIn("error=",self.client.post("/login", {"usuario":"president", "contrasena":"long password"}).url)

    def test_presidency_and_vice_presidency_are_read_only_across_modules(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for user in (self.president,self.vice):
            self.client.force_login(user)
            for path in ("/finanzas","/finanzas/comprobantes","/finanzas/exportar","/proyectos","/drive"):
                with self.subTest(user=user.username,path=path): self.assertEqual(self.client.get(path).status_code,200)
            self.assertEqual(self.client.get("/usuarios").status_code,403)
            self.assertEqual(self.client.post("/finanzas/egresos/registrar",{"cantidad":"1","concepto":"X","precio_unitario":"1"}).status_code,403)
            self.assertEqual(self.client.post("/proyectos/guardar",{"tipo":"note","titulo":"No","contenido":"No"}).status_code,403)
            self.assertEqual(self.client.post("/assets/upload",{"archivo":SimpleUploadedFile("a.txt",b"a")}).status_code,403)

    def test_existing_bcrypt_password_is_verified_and_upgraded(self):
        user = User.objects.create_user("legacy", "temporary password")
        user.password = bcrypt.hashpw(b"legacy password", bcrypt.gensalt()).decode().replace("$2b$", "$2a$", 1)
        user.save(update_fields=["password"])
        response = self.client.post("/login", {"usuario":"legacy", "contrasena":"legacy password"})
        self.assertEqual(response.status_code, 303)
        user.refresh_from_db()
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_unauthenticated_page_redirects_to_login(self):
        paths = ("/", "/finanzas", "/finanzas/comprobantes", "/finanzas/exportar", "/proyectos", "/proyectos/fases", "/drive", "/assets", "/assets/download?id=1", "/usuarios", "/roles")
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 303)
                self.assertTrue(response.url.startswith("/login?next="))

    def test_csrf_failure_uses_branded_error_page(self):
        client=Client(enforce_csrf_checks=True)
        response=client.post("/login",{"usuario":"admin","contrasena":"1234"})
        self.assertEqual(response.status_code,403)
        self.assertContains(response,"Solicitud bloqueada por seguridad",status_code=403)
        self.assertNotContains(response,"establece DEBUG",status_code=403)

    def test_logout_clears_session_and_protected_pages_redirect(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post("/logout").status_code, 303)
        response = self.client.get("/proyectos")
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.url.startswith("/login?next="))

    def test_admin_can_change_own_nip_without_losing_session(self):
        self.client.force_login(self.admin)
        response = self.client.post("/usuarios", {"id": self.admin.id, "usuario": "admin", "rol": "administrador", "acceso": "on", "contrasena": "NewAdminPass!2026", "accion": "guardar"})
        self.assertEqual(response.status_code, 303)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("NewAdminPass!2026"))
        self.assertEqual(self.client.get("/usuarios").status_code, 200)
        self.client.post("/logout")
        self.assertEqual(self.client.post("/login",{"usuario":"admin","contrasena":"correct horse battery"}).url,"/login?error=Usuario+o+contrase%C3%B1a+incorrectos.")
        self.assertEqual(self.client.post("/login",{"usuario":"admin","contrasena":"NewAdminPass!2026"}).status_code,303)

    def test_bootstrap_admin_does_not_reset_existing_password_unless_requested(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        self.admin.set_password("ExistingAdminPass!2026");self.admin.save(update_fields=["password"])
        with patch.dict("os.environ",{"ADMIN_USER":"admin","ADMIN_PASSWORD":"UpdatedAdminPass!2026"}):
            call_command("bootstrap_admin",stdout=StringIO())
            self.admin.refresh_from_db();self.assertTrue(self.admin.check_password("ExistingAdminPass!2026"))
            call_command("bootstrap_admin",reset_password=True,stdout=StringIO())
        self.admin.refresh_from_db();self.assertTrue(self.admin.check_password("UpdatedAdminPass!2026"))

    def test_role_denial_returns_403(self):
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get("/presidencia").status_code, 404)
        self.assertEqual(self.client.get("/recursos-humanos").status_code, 404)

    def test_account_role_update_invalidates_sessions(self):
        other=Client();other.force_login(self.other)
        key=other.session.session_key
        self.client.force_login(self.admin)
        response=self.client.post("/usuarios",{"id":self.other.id,"usuario":"other","rol":"finanzas","acceso":"on","accion":"guardar"})
        self.assertEqual(response.status_code,303)
        self.other.refresh_from_db()
        self.assertEqual(self.other.role_name,"finanzas")
        from django.contrib.sessions.models import Session
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_admin_user_tab_creates_and_rejects_accounts(self):
        self.client.force_login(self.admin)
        response=self.client.get("/usuarios")
        self.assertContains(response,"Usuarios")
        self.assertContains(response,"Crear cuenta")
        self.assertEqual(self.client.post("/usuarios",{"accion":"crear","usuario":"nuevo","contrasena":"1234","rol":"proyectos","acceso":"on"}).status_code,303)
        user=User.objects.get(username="nuevo")
        self.assertTrue(user.approved)
        self.assertEqual(user.role_name,"proyectos")
        self.assertEqual(self.client.post("/usuarios",{"id":user.id,"accion":"rechazar"}).status_code,303)
        user.refresh_from_db();self.assertFalse(user.approved);self.assertFalse(user.is_active);self.assertFalse(user.roles.exists())

    def test_user_update_conflict_is_reported_without_generic_400(self):
        self.client.force_login(self.admin)
        response=self.client.post("/usuarios",{"id":self.other.id,"usuario":"admin","rol":"finanzas","acceso":"on","accion":"guardar"})
        self.assertEqual(response.status_code,409)
        self.other.refresh_from_db();self.assertEqual(self.other.username,"other")

    def test_disabled_legacy_user_can_be_saved_without_selectable_role(self):
        from .models import UserRole
        self.other.roles.clear();self.other.roles.add(Role.objects.get(name="servicio_social"))
        self.client.force_login(self.admin)
        response=self.client.post("/usuarios",{"id":self.other.id,"usuario":"other","rol":"","accion":"guardar"})
        self.assertEqual(response.status_code,303)
        self.other.refresh_from_db();self.assertFalse(self.other.approved);self.assertFalse(self.other.is_active);self.assertFalse(self.other.roles.exists())

    def test_non_admin_cannot_see_users_page_or_menu_item(self):
        self.client.force_login(self.finance)
        response=self.client.get("/finanzas")
        self.assertNotContains(response,"/usuarios")
        self.assertEqual(self.client.get("/usuarios").status_code,403)

    def test_roles_see_projects_and_drive_but_only_finance_sees_finance(self):
        for user in (self.other, self.finance):
            self.client.force_login(user)
            self.assertEqual(self.client.get("/proyectos").status_code, 200)
            drive = self.client.get("/drive")
            self.assertEqual(drive.status_code, 200)
            self.assertContains(drive, "Proyectos")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/finanzas").status_code, 403)
        self.assertEqual(self.client.get("/finanzas/comprobantes").status_code, 403)
        self.assertEqual(self.client.get("/finanzas/exportar").status_code, 403)
        self.assertNotContains(self.client.get("/proyectos"), "/finanzas")

    def test_diffusion_can_upload_but_not_delete_drive_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import SharedAsset
        diffusion = User.objects.create_user("diffusion", "correct horse battery")
        diffusion.roles.add(Role.objects.get(name="difusion"))
        self.client.force_login(diffusion)
        response = self.client.post("/assets/upload", {"archivo": SimpleUploadedFile("difusion.txt", b"contenido")})
        self.assertEqual(response.status_code, 303)
        asset = SharedAsset.objects.get()
        self.assertEqual(self.client.post("/assets/delete", {"id": asset.id}).status_code, 403)

    def test_finance_validates_and_saves_cents(self):
        self.client.force_login(self.finance)
        response = self.client.post("/finanzas/ingresos", {"concepto":"Cuota", "monto":"12.34", "fecha":"2026-11-01", "origen":"Evento"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(Income.objects.get().cents, 1234)
        bad = self.client.post("/finanzas/ingresos", {"concepto":"Cuota", "monto":"12.345", "fecha":"2026-11-01"})
        self.assertEqual(bad.status_code, 303)
        self.assertEqual(Income.objects.count(),1)

    def test_finance_edit_missing_record_returns_feedback_not_server_error(self):
        self.client.force_login(self.finance)
        response=self.client.post("/finanzas/ingresos/editar",{"id":"999999","concepto":"Cuota","monto":"12.34"})
        self.assertEqual(response.status_code,303)

    def test_finance_export_keeps_xlsx_contract(self):
        self.client.force_login(self.finance)
        Income.objects.create(concept="=2+2",cents=1234,date="2026-11-01",origin="Evento",registered_by=self.finance)
        response=self.client.get("/finanzas/exportar")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response["Content-Type"],"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("reporte-finanzas.xlsx",response["Content-Disposition"])

    def test_purchase_defaults_date_and_exports_structured_totals(self):
        from django.utils import timezone
        from openpyxl import load_workbook
        self.client.force_login(self.finance)
        response=self.client.post("/finanzas/egresos/registrar",{"cantidad":"3","concepto":"Papelería","precio_unitario":"12.50"})
        self.assertEqual(response.status_code,303)
        expense=Expense.objects.get()
        self.assertEqual((expense.date.isoformat(),expense.cents),(timezone.localdate().isoformat(),3750))
        book=load_workbook(io.BytesIO(self.client.get("/finanzas/exportar").content),data_only=True)
        self.assertEqual(book["Compras"]["B2"].value,3)
        self.assertEqual(book["Compras"]["E2"].value,37.5)

    def test_editing_income_preserves_quantity_and_unit_price(self):
        self.client.force_login(self.finance)
        self.client.post("/finanzas/ingresos",{"productos_nombre":["Playera"],"productos_cantidad":["3"],"productos_precio":["80.00"]})
        income=Income.objects.get()
        response=self.client.post("/finanzas/ingresos/editar",{"id":income.id,"fecha":income.date.isoformat(),"cantidad":"3","precio_unitario":"80.00","concepto":"Playera editada","origen":"Evento","responsable":"Equipo","notas":"Venta"})
        self.assertEqual(response.status_code,303)
        income.refresh_from_db();self.assertEqual(income.cents,24000);self.assertIn("Cantidad: 3; precio unitario: 80.00;",income.notes)

    def test_projects_are_readable_but_only_project_role_edits(self):
        self.client.force_login(self.finance)
        self.assertEqual(self.client.post("/proyectos/guardar",{"tipo":"note","titulo":"Plan","contenido":"Revisar"}).status_code,403)
        project_user=User.objects.create_user("projects", "correct horse battery")
        project_user.roles.add(Role.objects.get(name="proyectos"))
        self.client.force_login(project_user)
        self.assertEqual(self.client.post("/proyectos/guardar",{"tipo":"note","titulo":"Plan","contenido":"Revisar"}).status_code,303)
        self.assertEqual(ProjectNote.objects.count(),1)

    def test_project_crud_edits_and_deletes(self):
        project_user=User.objects.create_user("projectcrud", "correct horse battery")
        project_user.roles.add(Role.objects.get(name="proyectos"))
        self.client.force_login(project_user)
        self.client.post("/proyectos/guardar",{"tipo":"inventory","articulo":"Carteles","cantidad":"2"})
        item=ProjectInventory.objects.get()
        self.assertEqual(self.client.post("/proyectos/guardar",{"tipo":"inventory","id":item.id,"articulo":"Carteles","cantidad":"5"}).status_code,303)
        item.refresh_from_db();self.assertEqual(item.quantity,5)
        self.assertEqual(self.client.post("/proyectos/eliminar",{"tipo":"inventory","id":item.id}).status_code,303)
        self.assertFalse(ProjectInventory.objects.exists())

    def test_finance_crud_for_finance_role_and_admin_access(self):
        self.client.force_login(self.finance)
        self.client.post("/finanzas/ingresos",{"concepto":"Cuota","monto":"10.00"})
        income=Income.objects.get()
        self.assertEqual(self.client.post("/finanzas/ingresos/editar",{"id":income.id,"concepto":"Cuota editada","monto":"15.00"}).status_code,303)
        income.refresh_from_db();self.assertEqual(income.cents,1500)
        self.assertEqual(self.client.post("/finanzas/ingresos/eliminar",{"id":income.id}).status_code,303)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/finanzas").status_code,200)

    def test_drive_upload_is_admin_only(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.finance)
        response=self.client.post("/assets/upload",{"archivo":SimpleUploadedFile("a.txt",b"contenido")})
        self.assertEqual(response.status_code,403)

    def test_drive_supports_multi_upload_preview_replace_trash_restore_and_purge(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone
        from datetime import timedelta
        from .models import SharedAsset, SharedAssetTrash
        self.client.force_login(self.admin)
        response=self.client.post("/assets/upload",{"archivos":[SimpleUploadedFile("one.txt",b"uno"),SimpleUploadedFile("two.txt",b"dos")]})
        self.assertEqual(response.status_code,303)
        self.assertEqual(SharedAsset.objects.count(),2)
        asset=SharedAsset.objects.get(name="one.txt")
        self.assertEqual(self.client.get(f"/assets/preview?id={asset.id}").status_code,200)
        response=self.client.post("/assets/replace",{"id":asset.id,"archivo":SimpleUploadedFile("one.txt",b"reemplazado")})
        self.assertEqual(response.status_code,303)
        self.assertEqual(SharedAssetTrash.objects.count(),1)
        self.assertEqual(SharedAsset.objects.count(),2)
        self.assertTrue(SharedAsset.objects.filter(name="one.txt").exists())
        retired=SharedAssetTrash.objects.get()
        self.assertEqual(self.client.post("/assets/restore",{"id":retired.id}).status_code,303)
        self.assertEqual(SharedAssetTrash.objects.count(),0)
        retired=SharedAssetTrash.objects.create(asset_id=999,name="old.txt",file="old.txt",content_type="text/plain",bytes=3,original_created_at=timezone.now())
        SharedAssetTrash.objects.filter(pk=retired.pk).update(deleted_at=timezone.now()-timedelta(days=16))
        retired.refresh_from_db()
        from .views import purge_expired_assets
        purge_expired_assets()
        self.assertFalse(SharedAssetTrash.objects.filter(pk=retired.pk).exists())

    def test_drive_search_filters_names_and_preview_extracts_docx_pptx_xlsx(self):
        import os, tempfile, zipfile
        from unittest.mock import patch
        from .models import SharedAsset
        self.client.force_login(self.admin)
        SharedAsset.objects.create(name="manual-final.docx",file="manual.docx",content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",bytes=100,uploaded_by=self.admin)
        SharedAsset.objects.create(name="other.svg",file="other.svg",content_type="image/svg+xml",bytes=20,uploaded_by=self.admin)
        response=self.client.get("/drive?q=manual")
        self.assertContains(response,"manual-final.docx")
        self.assertNotContains(response,"other.svg")
        with tempfile.TemporaryDirectory() as media:
            with zipfile.ZipFile(os.path.join(media,"manual.docx"),"w") as archive:
                archive.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Texto del documento</w:t></w:r></w:p></w:body></w:document>')
            with patch.dict(os.environ,{"MEDIA_ROOT":media}):
                preview=self.client.get("/assets/preview?id=%s"%SharedAsset.objects.get(name="manual-final.docx").id)
            self.assertEqual(preview.status_code,200)
            self.assertContains(preview,"Texto del documento")

    def test_pptx_and_xlsx_previews_extract_content(self):
        import os, tempfile, zipfile
        from unittest.mock import patch
        from .models import SharedAsset
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as media:
            fixtures={
                "slides.pptx":("ppt/slides/slide1.xml",'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Texto de diapositiva</a:t></p:sld>'),
                "book.xlsx":("xl/worksheets/sheet1.xml",'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>Valor de celda</t></is></c></row></sheetData></worksheet>'),
            }
            for filename,(member,xml) in fixtures.items():
                with zipfile.ZipFile(os.path.join(media,filename),"w") as archive:archive.writestr(member,xml)
            slides=SharedAsset.objects.create(name="slides.pptx",file="slides.pptx",content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",bytes=100,uploaded_by=self.admin)
            book=SharedAsset.objects.create(name="book.xlsx",file="book.xlsx",content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",bytes=100,uploaded_by=self.admin)
            with patch.dict(os.environ,{"MEDIA_ROOT":media}):
                slide_response=self.client.get("/assets/preview?id=%s"%slides.id)
                book_response=self.client.get("/assets/preview?id=%s"%book.id)
        self.assertContains(slide_response,"Texto de diapositiva")
        self.assertContains(book_response,"Valor de celda")

    def test_drive_preview_has_safe_fallback_for_unknown_binary(self):
        import os, tempfile
        from unittest.mock import patch
        from .models import SharedAsset
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as media:
            with open(os.path.join(media,"unknown.bin"),"wb") as file:file.write(b"\x00\x01\x02")
            asset=SharedAsset.objects.create(name="unknown.bin",file="unknown.bin",content_type="application/octet-stream",bytes=3,uploaded_by=self.admin)
            with patch.dict(os.environ,{"MEDIA_ROOT":media}):response=self.client.get("/assets/preview?id=%s"%asset.id)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Vista de contenido binario")
        self.assertContains(response,"00 01 02")

    def test_bulk_delete_removes_only_selected_project_items(self):
        first=ProjectNote.objects.create(title="Uno",body="1")
        second=ProjectNote.objects.create(title="Dos",body="2")
        self.client.force_login(self.admin)
        response=self.client.post("/proyectos/eliminar",{"tipo":"note","ids":[str(first.id),str(second.id)]})
        self.assertEqual(response.status_code,303)
        self.assertFalse(ProjectNote.objects.exists())

    def test_admin_can_edit_projects_and_upload_drive(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post("/proyectos/guardar",{"tipo":"note","titulo":"Admin","contenido":"Acceso total"}).status_code,303)
        response=self.client.post("/assets/upload",{"archivo":SimpleUploadedFile("admin.txt",b"contenido")})
        self.assertEqual(response.status_code,303)

    def test_project_dashboard_rejects_non_get(self):
        user = User.objects.create_user("projects", "correct horse battery")
        user.roles.add(Role.objects.get(name="proyectos"))
        self.client.force_login(user)
        self.assertEqual(self.client.post("/proyectos").status_code, 405)

    def test_all_active_page_templates_render(self):
        self.client.force_login(self.admin)
        paths = ("/", "/usuarios", "/roles", "/finanzas", "/finanzas/comprobantes", "/proyectos", "/assets", "/drive")
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


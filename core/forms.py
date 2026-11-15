from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import ProjectDeadline, ProjectInventory, ProjectNote


class MoneyFields(forms.Form):
    concepto = forms.CharField(max_length=200)
    fecha = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    responsable = forms.CharField(max_length=160, required=False)
    notas = forms.CharField(max_length=1000, required=False)

    def clean_fecha(self):
        return self.cleaned_data.get("fecha") or timezone.localdate()


class IncomeForm(MoneyFields):
    monto = forms.DecimalField(min_value=Decimal("0.01"), max_value=Decimal("1000000000"), max_digits=12, decimal_places=2)
    origen = forms.CharField(max_length=160, required=False)


class ExpenseForm(MoneyFields):
    cantidad = forms.CharField(required=False)
    precio_unitario = forms.DecimalField(min_value=Decimal("0.01"), max_value=Decimal("1000000000"), max_digits=12, decimal_places=2)
    categoria = forms.CharField(max_length=160, required=False)

    def clean_cantidad(self):
        raw = self.cleaned_data.get("cantidad") or "1"
        try:
            amount = Decimal(raw)
        except Exception as exc:
            raise forms.ValidationError("Cantidad no válida.") from exc
        if amount != amount.to_integral_value() or not 1 <= amount <= 1_000_000:
            raise forms.ValidationError("Cantidad no válida.")
        return int(amount)

    def clean(self):
        cleaned = super().clean()
        quantity = cleaned.get("cantidad")
        unit = cleaned.get("precio_unitario")
        if quantity and unit and quantity * unit > Decimal("1000000000"):
            self.add_error("precio_unitario", "El total excede el máximo permitido.")
        return cleaned


class ProjectDeadlineForm(forms.ModelForm):
    class Meta:
        model = ProjectDeadline
        fields = ("title", "due_date", "notes")
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
    due_date = forms.DateField(input_formats=["%Y-%m-%d"])


class ProjectInventoryForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1, max_value=1_000_000)
    notes = forms.CharField(required=False, max_length=2000)
    class Meta:
        model = ProjectInventory
        fields = ("item", "quantity", "notes")


class ProjectNoteForm(forms.ModelForm):
    body = forms.CharField(max_length=5000)
    class Meta:
        model = ProjectNote
        fields = ("title", "body")

    def clean_title(self):
        value = self.cleaned_data["title"].strip()
        if not value:
            raise forms.ValidationError("Este campo es obligatorio.")
        return value

    def clean_body(self):
        value = self.cleaned_data["body"].strip()
        if not value:
            raise forms.ValidationError("Este campo es obligatorio.")
        return value


from django import forms
from django.db.models import Q

from apps.catalog.models import Plan, PlanEntregable, Servicio
from apps.core.validators import formatear_rut

from .models import Prospecto

CLASE_CAMPO = "campo"
CLASE_CHECKBOX = "h-4 w-4 rounded border-gris-borde accent-vino"


class _EstiloCampoMixin:
    """Aplica a los widgets el mismo estilo que ya usan los inputs de cotizacion.html (.campo)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs["class"] = CLASE_CHECKBOX
            else:
                campo.widget.attrs["class"] = CLASE_CAMPO
                campo.widget.attrs["autocomplete"] = "off"

class ServicioForm(_EstiloCampoMixin, forms.ModelForm):
    class Meta:
        model = Servicio
        fields = ["nombre", "descripcion", "precio", "modalidad_cobro", "visible_en_sitio", "orden", "activo"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 4})}


class PlanForm(_EstiloCampoMixin, forms.ModelForm):
    class Meta:
        model = Plan
        fields = ["nombre", "descripcion", "precio_mensual", "precio_primer_mes", "destacado", "etiqueta", "visible_en_sitio", "orden", "activo"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 4})}


class PlanEntregableForm(_EstiloCampoMixin, forms.ModelForm):
    class Meta:
        model = PlanEntregable
        fields = ["tipo_entregable", "cantidad_mensual"]


PlanEntregableFormSet = forms.inlineformset_factory(
    Plan, PlanEntregable,
    form=PlanEntregableForm,
    extra=1, can_delete=True,
)


class ProspectoManualForm(_EstiloCampoMixin, forms.ModelForm):
    """Registro manual de un prospecto que llegó por otro canal (PC-PRO-02)."""

    class Meta:
        model = Prospecto
        fields = [
            "nombre", "empresa", "rut", "correo", "telefono", "como_nos_conocio",
            "rubro", "region", "tamano", "agencia_actual", "presupuesto", "situacion_actual",
        ]
        labels = {"como_nos_conocio": "Canal de origen", "rut": "RUT (empresa o persona)"}
        widgets = {"situacion_actual": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["como_nos_conocio"].required = True
        # Datos que quien registra a mano puede no conocer todavía.
        for nombre in ("tamano", "agencia_actual", "presupuesto"):
            self.fields[nombre].required = False

    def clean_rut(self):
        rut = self.cleaned_data.get("rut", "").strip()
        return formatear_rut(rut) if rut else ""

    def clean_correo(self):
        return self.cleaned_data["correo"].strip().lower()

    def buscar_duplicados(self):
        """Prospectos ya registrados con el mismo correo o el mismo RUT."""
        criterio = Q(correo__iexact=self.cleaned_data["correo"])
        if self.cleaned_data.get("rut"):
            criterio |= Q(rut=self.cleaned_data["rut"])
        return list(Prospecto.objects.filter(criterio).order_by("-creado_en")[:5])

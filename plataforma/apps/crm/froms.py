from django import forms

from apps.catalog.models import Plan, PlanEntregable, Servicio

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
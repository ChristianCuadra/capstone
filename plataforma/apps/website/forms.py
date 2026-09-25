from django import forms

from apps.catalog.models import Servicio
from apps.crm.models import OBJETIVOS, REDES, Prospecto


class SolicitudCotizacionForm(forms.ModelForm):
    """Formulario público de cotización: crea un Prospecto y alimenta el diagnóstico con IA."""

    objetivos = forms.MultipleChoiceField(choices=[(o, o) for o in OBJETIVOS], required=False, widget=forms.CheckboxSelectMultiple)
    redes_actuales = forms.MultipleChoiceField(choices=REDES, required=False, widget=forms.CheckboxSelectMultiple)
    servicios_requeridos = forms.ModelMultipleChoiceField(
        queryset=Servicio.objects.filter(activo=True), required=False, widget=forms.CheckboxSelectMultiple
    )
    acepta_privacidad = forms.BooleanField(required=True, error_messages={"required": "Debes aceptar para enviar la solicitud."})
    # Campo trampa anti-spam: oculto para personas; si viene con contenido, es un bot.
    sitio_empresa = forms.CharField(required=False)

    class Meta:
        model = Prospecto
        fields = [
            "nombre", "empresa", "correo", "telefono", "rubro", "region", "tamano", "agencia_actual", "presupuesto",
            "objetivos", "redes_actuales", "instagram", "sitio_web", "servicios_requeridos", "como_nos_conocio",
            "situacion_actual", "acepta_privacidad",
        ]
        widgets = {
            "tamano": forms.RadioSelect,
            "agencia_actual": forms.RadioSelect,
            "presupuesto": forms.RadioSelect,
        }
        error_messages = {
            "correo": {"invalid": "Revisa el correo: no parece válido."},
            "sitio_web": {"invalid": "Escribe la dirección completa, por ejemplo https://tumarca.cl"},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Radios y casillas se muestran como chips: el input queda oculto visualmente pero accesible.
        for campo in self.fields.values():
            if isinstance(campo.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                campo.widget.attrs["class"] = "sr-only"
        for nombre in ("rubro", "region", "tamano", "agencia_actual", "presupuesto"):
            self.fields[nombre].required = True
            self.fields[nombre].error_messages["required"] = "Elige una opción."
        for nombre in ("nombre", "empresa", "correo"):
            self.fields[nombre].error_messages["required"] = "Este dato es obligatorio."

    def clean_instagram(self):
        return self.cleaned_data["instagram"].strip().lstrip("@")

    def es_spam(self):
        return bool(self.cleaned_data.get("sitio_empresa"))

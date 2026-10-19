from django import forms

from apps.catalog.models import Servicio
from apps.crm.models import OBJETIVOS, REDES, Prospecto

from .models import ConfiguracionAgencia, Contenido, MetadatosPagina


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


class SolicitudAsesoriaForm(forms.ModelForm):
    """Asesoría estratégica gratuita: datos básicos de la empresa y su caso. Crea (o completa) un Prospecto."""

    acepta_privacidad = forms.BooleanField(required=True, error_messages={"required": "Debes aceptar para enviar tu caso."})
    sitio_empresa = forms.CharField(required=False)  # campo trampa anti-spam, igual que en la cotización

    class Meta:
        model = Prospecto
        fields = ["nombre", "empresa", "correo", "telefono", "rubro", "region", "tamano", "instagram", "situacion_actual", "acepta_privacidad"]
        widgets = {"tamano": forms.RadioSelect}
        error_messages = {"correo": {"invalid": "Revisa el correo: no parece válido."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tamano"].widget.attrs["class"] = "sr-only"
        for nombre in ("rubro", "region", "tamano"):
            self.fields[nombre].required = True
            self.fields[nombre].error_messages["required"] = "Elige una opción."
        for nombre in ("nombre", "empresa", "correo"):
            self.fields[nombre].error_messages["required"] = "Este dato es obligatorio."
        self.fields["situacion_actual"].required = True
        self.fields["situacion_actual"].error_messages["required"] = "Cuéntanos tu caso para poder orientarte."

    def clean_instagram(self):
        return self.cleaned_data["instagram"].strip().lstrip("@")

    def clean_correo(self):
        return self.cleaned_data["correo"].strip().lower()

    def es_spam(self):
        return bool(self.cleaned_data.get("sitio_empresa"))


class ContenidoForm(forms.ModelForm):
    """Formulario del CMS (PC-WEB-02). El slug se genera solo si se deja vacío."""

    class Meta:
        model = Contenido
        fields = ["titulo", "seccion", "resumen", "cuerpo", "imagen", "meta_titulo", "meta_descripcion", "estado", "orden"]
        widgets = {
            "resumen": forms.Textarea(attrs={"rows": 2}),
            "cuerpo": forms.Textarea(attrs={"rows": 10}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if nombre == "imagen":
                continue
            if isinstance(campo.widget, forms.CheckboxInput):
                continue
            campo.widget.attrs["class"] = "campo"
            campo.widget.attrs.setdefault("autocomplete", "off")


class MetadatosPaginaForm(forms.ModelForm):
    """Título y descripción SEO de una página fija (PC-SEO-01b). Vacío = texto por defecto del sitio."""

    class Meta:
        model = MetadatosPagina
        fields = ["meta_titulo", "meta_descripcion"]
        widgets = {"meta_descripcion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "campo"
            campo.widget.attrs["autocomplete"] = "off"
            campo.widget.attrs["maxlength"] = campo.max_length
            campo.widget.attrs["placeholder"] = "Vacío: se usa el texto actual del sitio"


class ConfiguracionAgenciaForm(forms.ModelForm):
    """Datos de contacto de la agencia (Panel → Configuración)."""

    class Meta:
        model = ConfiguracionAgencia
        fields = ["correo", "telefono", "whatsapp", "ciudad", "instagram_usuario", "linkedin_nombre", "linkedin_url"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "campo"
            campo.widget.attrs["autocomplete"] = "off"

    def clean_whatsapp(self):
        digitos = "".join(c for c in self.cleaned_data["whatsapp"] if c.isdigit())
        if not 8 <= len(digitos) <= 15:
            raise forms.ValidationError("Ingresa el número con código de país, solo números. Ej.: 56912345678.")
        return digitos

    def clean_instagram_usuario(self):
        import re

        usuario = self.cleaned_data["instagram_usuario"].strip().lstrip("@")
        if usuario and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", usuario):
            raise forms.ValidationError("El usuario solo puede tener letras, números, puntos y guiones bajos.")
        return usuario

    def clean_linkedin_url(self):
        url = self.cleaned_data["linkedin_url"].strip()
        if url and "linkedin.com/" not in url.lower():
            raise forms.ValidationError("Debe ser una dirección de linkedin.com.")
        return url

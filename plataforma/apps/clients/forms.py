import os

from django import forms

from .models import Cliente, DocumentoCliente

EXTENSIONES_PERMITIDAS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".txt"}
TAMANO_MAX_MB = 10

_INPUT = "mt-1 w-full rounded-xl border border-gris-borde bg-white px-3 py-2 text-sm focus:border-vino focus:outline-none"


class ClienteFichaForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nombre", "rut", "rubro", "region",
            "contacto_nombre", "contacto_correo", "contacto_telefono",
            "plan", "fecha_inicio_contrato", "forma_pago",
            "directrices_marca", "objetivos", "activo",
        ]
        widgets = {
            "fecha_inicio_contrato": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "directrices_marca": forms.Textarea(attrs={"rows": 5}),
            "objetivos": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if nombre != "activo":
                campo.widget.attrs.setdefault("class", _INPUT)
        self.fields["plan"].queryset = self.fields["plan"].queryset.filter(activo=True) | (
            self.fields["plan"].queryset.filter(pk=self.instance.plan_id) if self.instance.plan_id else self.fields["plan"].queryset.none()
        )


class DocumentoClienteForm(forms.ModelForm):
    class Meta:
        model = DocumentoCliente
        fields = ["nombre", "tipo", "archivo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", _INPUT)

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        extension = os.path.splitext(archivo.name)[1].lower()
        if extension not in EXTENSIONES_PERMITIDAS:
            raise forms.ValidationError("Formato no permitido. Usa PDF, Word, Excel, PowerPoint, imagen o texto.")
        if archivo.size > TAMANO_MAX_MB * 1024 * 1024:
            raise forms.ValidationError(f"El archivo supera los {TAMANO_MAX_MB} MB.")
        return archivo

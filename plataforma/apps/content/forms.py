from django import forms

from .models import PiezaContenido

TAMANO_MAX_MB = 50


class PiezaForm(forms.ModelForm):
    """Datos de una pieza del calendario editorial (crear y editar desde el panel).

    El cliente y el estado los valida la vista: el cliente según los visibles del usuario y el estado según la
    acción (crear o editar). Pasar por el formulario hace correr los validadores del modelo (extensión del archivo).
    """

    class Meta:
        model = PiezaContenido
        fields = ["titulo", "texto", "red_social", "fecha_programada", "archivo"]

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        # Solo se revisa el tamaño de un archivo recién subido; uno ya guardado no tiene que volver a cumplirlo.
        if archivo and hasattr(archivo, "content_type") and archivo.size > TAMANO_MAX_MB * 1024 * 1024:
            raise forms.ValidationError(f"El archivo supera los {TAMANO_MAX_MB} MB.")
        return archivo

    def errores_texto(self):
        """Errores en una línea, para mostrarlos con messages (el formulario vive en un modal del panel)."""
        partes = []
        for campo, errores in self.errors.items():
            etiqueta = self.fields[campo].label if campo in self.fields else ""
            partes.append(f"{etiqueta.capitalize()}: {' '.join(errores)}" if etiqueta else " ".join(errores))
        return " ".join(partes)

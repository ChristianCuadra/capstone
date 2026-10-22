"""Formularios de gestión de usuarios (panel interno, solo Administradora)."""

from django import forms

from .models import Rol, User


class UsuarioForm(forms.ModelForm):
    """Alta/edición de usuarios con rol (Alcance 4.3, CU-08).

    La contraseña es opcional al editar (se deja igual si no se escribe una nueva)
    y obligatoria al crear.
    """

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
        help_text="Al editar, déjala vacía para no cambiarla.",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "is_staff",
            "is_active",
            "cliente",
            "clientes_asignados",
        ]
        labels = {
            "username": "Usuario",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "is_staff": "Es del equipo de la agencia (acceso al panel interno)",
            "is_active": "Cuenta activa",
            "cliente": "Empresa (para roles Cliente aprobador / Cliente lector)",
            "clientes_asignados": "Clientes asignados (para Colaboradora)",
        }
        widgets = {
            "clientes_asignados": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, es_nuevo=False, **kwargs):
        self.es_nuevo = es_nuevo
        super().__init__(*args, **kwargs)
        if self.es_nuevo:
            self.fields["password"].required = True

        # El modelo permite estos campos en blanco (para no romper cuentas ya
        # existentes sin rol), pero en este formulario sí son obligatorios.
        # OJO: se deja la opción en blanco del selector de Rol (no se le quitan
        # choices) para que el usuario tenga que elegir uno a propósito; si se
        # quita esa opción, el navegador preselecciona el primero de la lista
        # sin que nadie lo haya elegido, y el required=True nunca se dispara.
        for nombre in ("rol", "first_name", "last_name", "email"):
            self.fields[nombre].required = True

        texto = "mt-1.5 w-full rounded-xl border border-gris-borde bg-white px-3 py-2.5 text-sm"
        casilla = "h-4 w-4 rounded border-gris-borde text-vino focus:ring-vino"
        for nombre, campo in self.fields.items():
            if isinstance(campo.widget, (forms.CheckboxInput,)):
                campo.widget.attrs.setdefault("class", casilla)
            elif isinstance(campo.widget, forms.CheckboxSelectMultiple):
                pass  # se renderiza como lista de checkboxes, ver template
            else:
                campo.widget.attrs.setdefault("class", texto)

    def clean_email(self):
        # Igual que en el modelo: se normaliza aquí también para no depender
        # solo del save() del modelo al validar duplicados con case distinto.
        email = self.cleaned_data.get("email", "")
        return email.lower()

    def clean(self):
        cleaned = super().clean()
        rol = cleaned.get("rol")
        cliente = cleaned.get("cliente")
        clientes_asignados = cleaned.get("clientes_asignados")
        if rol in (Rol.CLIENTE_APROBADOR, Rol.CLIENTE_LECTOR) and not cliente:
            self.add_error("cliente", "Los roles de cliente deben tener una empresa asociada.")
        if rol in (Rol.CLIENTE_APROBADOR, Rol.CLIENTE_LECTOR) and cleaned.get("is_staff"):
            self.add_error("is_staff", "Un usuario cliente no puede tener acceso al panel interno.")
        if rol == Rol.COLABORADORA and clientes_asignados is not None and not clientes_asignados:
            self.add_error("clientes_asignados", "La colaboradora debe tener al menos un cliente asignado.")
        return cleaned

    def save(self, commit=True):
        usuario = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            usuario.set_password(password)
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


class InvitacionClienteForm(forms.Form):
    """Crear la cuenta de una persona del cliente y enviarle la invitación (PC-AUT-07).

    Sin contraseña: la define la propia persona desde el enlace de activación.
    """

    ROLES = [
        (Rol.CLIENTE_APROBADOR, "Cliente aprobador · aprueba o pide cambios al contenido"),
        (Rol.CLIENTE_LECTOR, "Cliente lector · solo consulta"),
    ]

    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    email = forms.EmailField(label="Correo")
    rol = forms.ChoiceField(label="Rol", choices=ROLES, initial=Rol.CLIENTE_APROBADOR)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "mt-1 w-full rounded-xl border border-gris-borde bg-white px-3 py-2 text-sm")
        self.fields["email"].widget.attrs["autocomplete"] = "off"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo. Revísalo en Usuarios.")
        return email

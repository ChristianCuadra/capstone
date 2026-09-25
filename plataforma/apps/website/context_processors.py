def agencia(request):
    """Datos de contacto de la agencia, usados en navbar y footer de todas las páginas."""
    # TODO: Supabase - tabla agencia_config (fila única, editable desde "Contenido del sitio")
    # Nombre y dominio según el Documento de Alcance. Correo y teléfono: por confirmar con la agencia.
    return {
        "agencia": {
            "nombre": "Agencia Cosmopolitan",
            "descriptor": "Marketing digital",
            "dominio": "agenciacosmopolitan.cl",
            "correo": "hola@agenciacosmopolitan.cl",
            "telefono": "+56 9 8765 4321",
            # Redes: None = no se muestran. Completar con las URLs reales cuando la agencia las confirme.
            "instagram": None,  # {"usuario": "@…", "url": "https://instagram.com/…"}
            "linkedin": None,  # {"nombre": "…", "url": "https://linkedin.com/company/…"}
            "ciudad": "Santiago, Chile",
            # El menú muestra «Casos» solo cuando haya casos reales publicados.
            "mostrar_casos": False,
        }
    }

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class PortalTests(TestCase):
    def test_exige_login(self):
        respuesta = self.client.get(reverse("content:calendario"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("account_login"), respuesta["Location"])

    def test_paginas_vacias_sin_datos_de_ejemplo(self):
        self.client.force_login(get_user_model().objects.create_user("cliente", "cliente@x.cl", "x"))
        for nombre in ("content:calendario", "content:aprobacion", "content:metricas"):
            with self.subTest(nombre=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotContains(respuesta, "Café Kütral")
                self.assertNotContains(respuesta, "pan amasado")

    def test_navegacion_de_meses(self):
        self.client.force_login(get_user_model().objects.create_user("cliente", "cliente@x.cl", "x"))
        respuesta = self.client.get(reverse("content:calendario"), {"mes": "2026-01"})
        self.assertEqual(respuesta.context["mes_anterior"], "2025-12")
        self.assertEqual(respuesta.context["mes_siguiente"], "2026-02")

    def test_raiz_del_portal_redirige_al_calendario(self):
        self.assertRedirects(self.client.get("/portal/"), reverse("content:calendario"), target_status_code=302)

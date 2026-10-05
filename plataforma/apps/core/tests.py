
# Create your tests here.
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .validators import formatear_rut


class RutTests(SimpleTestCase):
    def test_rut_valido_se_normaliza(self):
        self.assertEqual(formatear_rut("123456785"), "12.345.678-5")
        self.assertEqual(formatear_rut("12.345.678-5"), "12.345.678-5")
        self.assertEqual(formatear_rut("7654321-6"), "7.654.321-6")
        self.assertEqual(formatear_rut("1.000.005-k"), "1.000.005-K")
        self.assertEqual(formatear_rut("1000013-0"), "1.000.013-0")

    def test_rut_invalido_se_rechaza(self):
        for valor in ("12.345.678-9", "abc", "1-9", "12345678", "123456789012-3"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    formatear_rut(valor)

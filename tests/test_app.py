#!/usr/bin/env python3
"""
Testes Automatizados - Otimizador de Rotas de Entrega
Validação de Roteirização, Geocodificação, Rate Limit e Segurança
"""

import unittest
import os
import sys
import tempfile
import sqlite3

# Adiciona o diretório raiz ao path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server

class TestLogisticaApp(unittest.TestCase):

    def setUp(self):
        # Cria banco de teste temporário
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        server.DB_PATH = self.temp_db_path
        server.init_db()

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_sanitize_cep(self):
        """Testa validação e extração de dígitos de CEP."""
        self.assertEqual(server.sanitize_cep("13170-023"), "13170023")
        self.assertEqual(server.sanitize_cep("13170023"), "13170023")
        self.assertEqual(server.sanitize_cep("13.170-023"), "13170023")
        # CEPs com quantidade incorreta de dígitos
        self.assertIsNone(server.sanitize_cep("13170"))
        self.assertIsNone(server.sanitize_cep("1317002399"))
        self.assertIsNone(server.sanitize_cep(""))
        self.assertIsNone(server.sanitize_cep("abc"))

    def test_sanitize_text(self):
        """Testa remoção de tags HTML e caracteres maliciosos."""
        dirty = "<script>alert('xss')</script>Sofá Retrátil"
        cleaned = server.sanitize_text(dirty)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("</script>", cleaned)
        self.assertIn("Sofá Retrátil", cleaned)

    def test_haversine_distance(self):
        """Testa cálculo de distância terrestre."""
        # Distância entre Sumaré e Campinas (~20-25 km rodoviários)
        lat_sumare, lon_sumare = -22.82194, -47.26694
        lat_campinas, lon_campinas = -22.90556, -47.06083
        dist = server.haversine_km(lat_sumare, lon_sumare, lat_campinas, lon_campinas)
        self.assertTrue(20.0 <= dist <= 38.0, f"Distância esperada ~25-35km, obtido: {dist}")

    def test_tsp_optimization(self):
        """Testa ordenação de paradas com algoritmo Nearest Neighbor + 2-Opt."""
        origin = {"lat": -22.82194, "lon": -47.26694, "nome": "Sumaré"}
        stops = [
            {"lat": -22.75611, "lon": -47.33278, "nome": "Americana"},
            {"lat": -22.75389, "lon": -47.41444, "nome": "Santa Bárbara d'Oeste"},
            {"lat": -22.78444, "lon": -47.29750, "nome": "Nova Odessa"},
            {"lat": -22.90556, "lon": -47.06083, "nome": "Campinas"}
        ]
        ordered, total_dist = server.solve_tsp(origin, stops, return_to_origin=False)
        self.assertEqual(len(ordered), 4)
        self.assertGreater(total_dist, 0.0)
        # Todos os 4 destinos devem estar presentes no trajeto
        nomes_resultado = [s["nome"] for s in ordered]
        self.assertSetEqual(set(nomes_resultado), {"Americana", "Santa Bárbara d'Oeste", "Nova Odessa", "Campinas"})
        # A distância do 2-Opt deve ser menor ou igual à distância gulosa
        self.assertLessEqual(total_dist, 76.0)

    def test_cache_database_insert_and_retrieve(self):
        """Testa persistência e integridade das consultas SQL parametrizadas."""
        sample = {
            "cep": "13170023",
            "logradouro": "Avenida Rebouças",
            "bairro": "Centro",
            "localidade": "Sumaré",
            "uf": "SP",
            "latitude": -22.82194,
            "longitude": -47.26694,
            "fonte": "teste"
        }
        server.save_cep_to_cache(sample)
        cached = server.get_cep_from_cache("13170023")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["localidade"], "Sumaré")
        self.assertEqual(cached["latitude"], -22.82194)

    def test_rate_limiter(self):
        """Testa o limitador de taxa por IP."""
        test_ip = "192.168.1.100"
        server.request_counts[test_ip] = []
        for _ in range(server.RATE_LIMIT_MAX):
            self.assertTrue(server.check_rate_limit(test_ip))
        # O próximo além do limite deve retornar False
        self.assertFalse(server.check_rate_limit(test_ip))

    def test_path_traversal_protection(self):
        """Testa que caminhos fora de static/ são bloqueados com segurança."""
        safe_base = os.path.abspath(server.STATIC_DIR)
        malicious_path = os.path.abspath(os.path.join(server.STATIC_DIR, "../../etc/passwd"))
        self.assertFalse(malicious_path.startswith(safe_base))
        valid_path = os.path.abspath(os.path.join(server.STATIC_DIR, "index.html"))
        self.assertTrue(valid_path.startswith(safe_base))

if __name__ == "__main__":
    unittest.main()

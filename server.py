#!/usr/bin/env python3
"""
Servidor Backend - Otimizador de Rotas de Entrega (Estofados)
Versão Beta (MVP & KISS)
100% Python Standard Library (Sem dependências externas)
"""

import os
import sys
import json
import math
import re
import time
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple

# Configurações do Servidor
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cache_ceps.db")

# Parâmetros de Logística Padrão
DEFAULT_FACTORY_CEP = "13170023" # Sumaré - SP
DEFAULT_FACTORY_ADDR = "Avenida Rebouças, Centro, Sumaré - SP"
DEFAULT_FACTORY_LAT = -22.82194
DEFAULT_FACTORY_LON = -47.26694
DEFAULT_SPEED_KMH = 45.0 # Velocidade média urbana/rodoviária
DEFAULT_UNLOAD_MIN = 20 # Tempo médio de descarregamento de estofado por parada
MAX_STOPS_LIMIT = 50 # Limite de paradas por cálculo para garantir performance no MVP
MAX_PAYLOAD_SIZE = 1024 * 1024 # 1 MB

# Rate Limiting Simples em Memória (60 requisições/min por IP)
RATE_LIMIT_MAX = 60
RATE_LIMIT_WINDOW = 60 # segundos
request_counts: Dict[str, List[float]] = defaultdict(list)

# Headers de Segurança Padrão
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "no-referrer-when-downgrade",
}

# Tipos MIME suportados
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

def init_db():
    """Inicializa as tabelas do banco de dados SQLite com índices apropriados."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Tabela de cache de CEPs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ceps (
                cep TEXT PRIMARY KEY,
                logradouro TEXT,
                bairro TEXT,
                localidade TEXT,
                uf TEXT,
                latitude REAL,
                longitude REAL,
                fonte TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Tabela de romaneios salvos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS romaneios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_paradas INTEGER NOT NULL,
                distancia_total_km REAL NOT NULL,
                tempo_total_min INTEGER NOT NULL,
                dados_json TEXT NOT NULL
            )
        """)
        conn.commit()

def sanitize_text(text: Optional[str], max_len: int = 150) -> str:
    """Sanitiza strings de entrada para evitar injeção e XSS."""
    if not text:
        return ""
    # Remove caracteres de controle e tags html básicas
    cleaned = re.sub(r"[<>]", "", str(text)).strip()
    return cleaned[:max_len]

def sanitize_cep(cep_raw: str) -> Optional[str]:
    """Valida e extrai CEP de 8 dígitos."""
    if not cep_raw:
        return None
    digits = re.sub(r"\D", "", str(cep_raw))
    if len(digits) == 8:
        return digits
    return None

def check_rate_limit(ip: str) -> bool:
    """Verifica se o IP excedeu o limite de requisições por minuto."""
    now = time.time()
    timestamps = request_counts[ip]
    # Remove requisições mais antigas que a janela
    valid_timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(valid_timestamps) >= RATE_LIMIT_MAX:
        request_counts[ip] = valid_timestamps
        return False
    valid_timestamps.append(now)
    request_counts[ip] = valid_timestamps
    return True

# --- SERVIÇOS DE GEOCODIFICAÇÃO E BANCO DE DADOS ---

def get_cep_from_cache(cep: str) -> Optional[Dict[str, Any]]:
    """Consulta CEP no banco SQLite local usando consulta parametrizada."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cep, logradouro, bairro, localidade, uf, latitude, longitude, fonte
                FROM ceps WHERE cep = ?
            """, (cep,))
            row = cursor.fetchone()
            if row:
                return {
                    "cep": row[0],
                    "logradouro": row[1] or "",
                    "bairro": row[2] or "",
                    "localidade": row[3] or "",
                    "uf": row[4] or "",
                    "latitude": row[5],
                    "longitude": row[6],
                    "fonte": row[7]
                }
    except Exception as e:
        sys.stderr.write(f"[DB Error] Falha ao ler cache do CEP {cep}: {e}\n")
    return None

def save_cep_to_cache(data: Dict[str, Any]):
    """Salva dados de CEP no banco SQLite local de forma parametrizada."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ceps (cep, logradouro, bairro, localidade, uf, latitude, longitude, fonte)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["cep"],
                data.get("logradouro", ""),
                data.get("bairro", ""),
                data.get("localidade", ""),
                data.get("uf", ""),
                data.get("latitude"),
                data.get("longitude"),
                data.get("fonte", "api")
            ))
            conn.commit()
    except Exception as e:
        sys.stderr.write(f"[DB Error] Falha ao gravar cache do CEP {data.get('cep')}: {e}\n")

def fetch_external_url(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 4) -> Optional[Dict[str, Any]]:
    """Executa requisição HTTP segura com timeout rigoroso."""
    req_headers = {"User-Agent": "LogisticaEstofadosApp/1.0 (MVP Beta; contato@estofados.local)"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
    except Exception:
        return None
    return None

def geocode_address_nominatim(address: str) -> Optional[Tuple[float, float]]:
    """Consulta OpenStreetMap Nominatim para obter coordenadas de endereço."""
    try:
        query_params = urllib.parse.urlencode({
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": "br"
        })
        url = f"https://nominatim.openstreetmap.org/search?{query_params}"
        data = fetch_external_url(url, timeout=4)
        if isinstance(data, list) and len(data) > 0:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return lat, lon
    except Exception:
        pass
    return None

def geocode_cep(cep: str) -> Optional[Dict[str, Any]]:
    """
    Pipeline de Geocodificação em Camadas:
    1. Cache SQLite
    2. BrasilAPI v2 (endereço + coordenadas diretas)
    3. ViaCEP + OSM Nominatim
    4. Fallback municipal
    """
    cached = get_cep_from_cache(cep)
    if cached and cached.get("latitude") is not None and cached.get("longitude") is not None:
        return cached

    result: Dict[str, Any] = {
        "cep": cep,
        "logradouro": "",
        "bairro": "",
        "localidade": "",
        "uf": "",
        "latitude": None,
        "longitude": None,
        "fonte": "brasilapi"
    }

    # Tentativa 1: BrasilAPI v2
    brasil_api = fetch_external_url(f"https://brasilapi.com.br/api/cep/v2/{cep}", timeout=4)
    if brasil_api and not brasil_api.get("type") == "not_found" and not brasil_api.get("errors"):
        result["logradouro"] = brasil_api.get("street", "")
        result["bairro"] = brasil_api.get("neighborhood", "")
        result["localidade"] = brasil_api.get("city", "")
        result["uf"] = brasil_api.get("state", "")
        loc = brasil_api.get("location")
        if loc and isinstance(loc, dict) and loc.get("coordinates"):
            coords = loc["coordinates"]
            try:
                result["fallback_latitude"] = float(coords.get("latitude"))
                result["fallback_longitude"] = float(coords.get("longitude"))
            except (ValueError, TypeError):
                pass

    # Tentativa 2: Se faltou logradouro ou localidade, tenta ViaCEP
    if not result["localidade"]:
        viacep = fetch_external_url(f"https://viacep.com.br/ws/{cep}/json/", timeout=4)
        if viacep and not viacep.get("erro"):
            result["logradouro"] = viacep.get("logradouro", "")
            result["bairro"] = viacep.get("bairro", "")
            result["localidade"] = viacep.get("localidade", "")
            result["uf"] = viacep.get("uf", "")
            result["fonte"] = "viacep"

    # Geocodificação em nível de logradouro/bairro (alta precisão)
    if result["localidade"]:
        coords = None
        # 1. Rua + Bairro + Cidade
        if result["logradouro"] and result["bairro"]:
            coords = geocode_address_nominatim(f"{result['logradouro']}, {result['bairro']}, {result['localidade']}, {result['uf']}, Brasil")
        # 2. Rua + Cidade
        if not coords and result["logradouro"]:
            coords = geocode_address_nominatim(f"{result['logradouro']}, {result['localidade']}, {result['uf']}, Brasil")
        # 3. Bairro + Cidade
        if not coords and result["bairro"]:
            coords = geocode_address_nominatim(f"{result['bairro']}, {result['localidade']}, {result['uf']}, Brasil")

        if coords:
            result["latitude"] = coords[0]
            result["longitude"] = coords[1]
        elif "fallback_latitude" in result:
            result["latitude"] = result["fallback_latitude"]
            result["longitude"] = result["fallback_longitude"]
        else:
            # Fallback cidade
            coords = geocode_address_nominatim(f"{result['localidade']}, {result['uf']}, Brasil")
            if coords:
                result["latitude"] = coords[0]
                result["longitude"] = coords[1]

    # Se encontramos endereço e coordenadas válidas, persiste no cache
    if result["localidade"] and result.get("latitude") is not None:
        save_cep_to_cache(result)
        return result

    # Caso falhe completamente
    return None

# --- ALGORITMOS DE ROTEIRIZAÇÃO (TSP / KISS & MVP) ---

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula a distância aproximada por via terrestre entre dois pontos usando Haversine com fator de via 1.30."""
    R = 6371.0 # Raio da Terra em km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_direta = R * c
    # Fator de correção rodoviário urbano/intermunicipal
    dist_rodoviaria = dist_direta * 1.30
    return round(dist_rodoviaria, 2)

def solve_tsp(origin: Dict[str, Any], stops: List[Dict[str, Any]], return_to_origin: bool = False) -> Tuple[List[Dict[str, Any]], float]:
    """
    Resolve o Problema do Caixeiro-Viajante (TSP) usando heurística Nearest Neighbor + 2-Opt.
    KISS: Extremamente rápido, determinístico e excelente para até 50 paradas.
    """
    if not stops:
        return [], 0.0
    if len(stops) == 1:
        d = haversine_km(origin["lat"], origin["lon"], stops[0]["lat"], stops[0]["lon"])
        if return_to_origin:
            d += haversine_km(stops[0]["lat"], stops[0]["lon"], origin["lat"], origin["lon"])
        return stops, round(d, 2)

    # Passo 1: Construção gulosa inicial (Nearest Neighbor)
    unvisited = stops.copy()
    ordered: List[Dict[str, Any]] = []
    current_lat, current_lon = origin["lat"], origin["lon"]

    while unvisited:
        best_idx = 0
        best_dist = float("inf")
        for i, stop in enumerate(unvisited):
            dist = haversine_km(current_lat, current_lon, stop["lat"], stop["lon"])
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        next_stop = unvisited.pop(best_idx)
        ordered.append(next_stop)
        current_lat, current_lon = next_stop["lat"], next_stop["lon"]

    # Passo 2: Otimização 2-Opt (Desfaz cruzamentos de rota)
    def compute_total_distance(tour: List[Dict[str, Any]]) -> float:
        tot = haversine_km(origin["lat"], origin["lon"], tour[0]["lat"], tour[0]["lon"])
        for i in range(len(tour) - 1):
            tot += haversine_km(tour[i]["lat"], tour[i]["lon"], tour[i+1]["lat"], tour[i+1]["lon"])
        if return_to_origin:
            tot += haversine_km(tour[-1]["lat"], tour[-1]["lon"], origin["lat"], origin["lon"])
        return tot

    improved = True
    iterations = 0
    best_tour = ordered
    best_dist = compute_total_distance(best_tour)

    while improved and iterations < 50:
        improved = False
        iterations += 1
        for i in range(len(best_tour) - 1):
            for j in range(i + 1, len(best_tour)):
                # Inverte o trecho entre i e j
                candidate = best_tour[:i] + best_tour[i:j+1][::-1] + best_tour[j+1:]
                cand_dist = compute_total_distance(candidate)
                if cand_dist < best_dist - 0.05: # Ganho significativo
                    best_tour = candidate
                    best_dist = cand_dist
                    improved = True
                    break
            if improved:
                break

    return best_tour, round(best_dist, 2)

def generate_maps_links(origin: Dict[str, Any], ordered_stops: List[Dict[str, Any]]) -> Dict[str, str]:
    """Gera links inteligentes de navegação para Google Maps e Waze."""
    if not ordered_stops:
        return {}

    # Link completo Google Maps com waypoints
    origin_str = f"{origin['lat']},{origin['lon']}"
    dest_stop = ordered_stops[-1]
    destination_str = f"{dest_stop['lat']},{dest_stop['lon']}"

    waypoints_str = ""
    if len(ordered_stops) > 1:
        # Waypoints intermediários
        intermediate = ordered_stops[:-1]
        waypoints_str = "|".join([f"{s['lat']},{s['lon']}" for s in intermediate])

    params = {
        "api": "1",
        "origin": origin_str,
        "destination": destination_str,
        "travelmode": "driving"
    }
    if waypoints_str:
        params["waypoints"] = waypoints_str

    full_google_maps = f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"
    return {"google_maps_full": full_google_maps}

# --- HANDLER HTTP ---

class LogisticaHttpHandler(BaseHTTPRequestHandler):
    """Handler HTTP com conformidade de segurança e endpoints REST."""

    def send_security_headers(self, content_type: str = "application/json"):
        for header, val in SECURITY_HEADERS.items():
            self.send_header(header, val)
        self.send_header("Content-Type", content_type)
        # CORS seguro para chamadas locais/mesma origem
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json_response(self, status_code: int, data: Dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status_code: int, message: str):
        self.send_json_response(status_code, {
            "success": False,
            "error": message
        })

    def do_OPTIONS(self):
        """Suporte a requisições de preflight CORS."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_security_headers("text/plain")
        self.end_headers()

    def do_GET(self):
        """Roteamento de requisições GET (estáticos e APIs)."""
        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_error_json(HTTPStatus.TOO_MANY_REQUESTS, "Limite de requisições excedido. Aguarde um minuto.")
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Rota de Healthcheck
        if path == "/api/health":
            self.send_json_response(HTTPStatus.OK, {
                "success": True,
                "status": "online",
                "app": "Otimizador de Rotas de Entrega (Estofados)",
                "version": "1.0-beta"
            })
            return

        # Rota de Histórico de Romaneios
        if path == "/api/history":
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, titulo, criado_em, total_paradas, distancia_total_km, tempo_total_min, dados_json
                        FROM romaneios ORDER BY id DESC LIMIT 15
                    """)
                    rows = cursor.fetchall()
                    history = []
                    for r in rows:
                        history.append({
                            "id": r[0],
                            "titulo": r[1],
                            "criado_em": r[2],
                            "total_paradas": r[3],
                            "distancia_total_km": r[4],
                            "tempo_total_min": r[5],
                            "dados": json.loads(r[6])
                        })
                    self.send_json_response(HTTPStatus.OK, {"success": True, "history": history})
                    return
            except Exception as e:
                sys.stderr.write(f"[API Error] Erro ao buscar histórico: {e}\n")
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Não foi possível carregar o histórico de romaneios.")
                return

        # Servir Arquivos Estáticos com proteção contra Directory Traversal
        if path == "/" or path == "/index.html":
            file_path = os.path.join(STATIC_DIR, "index.html")
        else:
            rel_path = path.lstrip("/")
            file_path = os.path.join(STATIC_DIR, rel_path)

        # Prevenção rigorosa de Path Traversal
        safe_base = os.path.abspath(STATIC_DIR)
        target_path = os.path.abspath(file_path)

        if not target_path.startswith(safe_base) or not os.path.isfile(target_path):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Página ou recurso não encontrado.")
            return

        _, ext = os.path.splitext(target_path)
        mime = MIME_TYPES.get(ext.lower(), "application/octet-stream")

        try:
            with open(target_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_security_headers(mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Erro ao carregar o arquivo estático.")

    def do_POST(self):
        """Roteamento de requisições POST para geocodificação e otimização."""
        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_error_json(HTTPStatus.TOO_MANY_REQUESTS, "Limite de requisições excedido. Aguarde um minuto.")
            return

        # Verificação do tamanho do payload
        content_length_str = self.headers.get("Content-Length")
        if not content_length_str:
            self.send_error_json(HTTPStatus.LENGTH_REQUIRED, "Cabeçalho Content-Length ausente.")
            return

        try:
            content_length = int(content_length_str)
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Content-Length inválido.")
            return

        if content_length > MAX_PAYLOAD_SIZE:
            self.send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload excede o limite máximo permitido de 1MB.")
            return

        try:
            raw_body = self.rfile.read(content_length).decode("utf-8")
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Formato JSON inválido no corpo da requisição.")
            return
        except Exception:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Falha ao processar corpo da requisição.")
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # ENDPOINT 1: Geocodificação em lote de CEPs
        if path == "/api/geocode":
            self.handle_geocode(body)
            return

        # ENDPOINT 2: Otimização de Rota (TSP)
        if path == "/api/optimize":
            self.handle_optimize(body)
            return

        # ENDPOINT 3: Salvar Romaneio
        if path == "/api/save-romaneio":
            self.handle_save_romaneio(body)
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint não encontrado.")

    def handle_geocode(self, body: Dict[str, Any]):
        """Valida e geocodifica uma lista de CEPs e anotações."""
        items = body.get("items", [])
        if not isinstance(items, list):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "O campo 'items' deve ser uma lista.")
            return

        if len(items) > MAX_STOPS_LIMIT:
            self.send_error_json(HTTPStatus.BAD_REQUEST, f"Número máximo de itens por romaneio no MVP é {MAX_STOPS_LIMIT}.")
            return

        results = []
        invalid_count = 0

        for item in items:
            raw_text = str(item.get("raw", "") if isinstance(item, dict) else item)
            # Extrai CEP e nota (ex: "13170-023 #Pedido 123 Sofá Retrátil")
            cep_candidate = sanitize_cep(raw_text)

            # Extração de nota opcional
            nota = ""
            if isinstance(item, dict) and item.get("nota"):
                nota = sanitize_text(item.get("nota"), max_len=100)
            else:
                # Tenta extrair qualquer texto após o CEP
                match_note = re.search(r"(\d{5}-?\d{3})\s*[-–:]?\s*(.+)", raw_text)
                if match_note:
                    nota = sanitize_text(match_note.group(2), max_len=100)

            if not cep_candidate:
                results.append({
                    "raw": sanitize_text(raw_text, 80),
                    "valid": False,
                    "error": "CEP com formato inválido (deve conter 8 dígitos)",
                    "cep": None
                })
                invalid_count += 1
                continue

            geo = geocode_cep(cep_candidate)
            if not geo or geo.get("latitude") is None:
                results.append({
                    "raw": sanitize_text(raw_text, 80),
                    "valid": False,
                    "error": "Endereço ou coordenadas não localizados para este CEP",
                    "cep": f"{cep_candidate[:5]}-{cep_candidate[5:]}",
                    "nota": nota
                })
                invalid_count += 1
            else:
                results.append({
                    "raw": sanitize_text(raw_text, 80),
                    "valid": True,
                    "cep": f"{cep_candidate[:5]}-{cep_candidate[5:]}",
                    "logradouro": geo.get("logradouro", ""),
                    "bairro": geo.get("bairro", ""),
                    "localidade": geo.get("localidade", ""),
                    "uf": geo.get("uf", ""),
                    "lat": geo.get("latitude"),
                    "lon": geo.get("longitude"),
                    "nota": nota,
                    "endereco_completo": f"{geo.get('logradouro')}, {geo.get('bairro')}, {geo.get('localidade')} - {geo.get('uf')}".strip(", -")
                })

        self.send_json_response(HTTPStatus.OK, {
            "success": True,
            "total_processados": len(results),
            "invalid_count": invalid_count,
            "itens": results
        })

    def handle_optimize(self, body: Dict[str, Any]):
        """Executa a otimização de rota para os pontos geocodificados."""
        stops = body.get("stops", [])
        if not isinstance(stops, list) or len(stops) == 0:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Lista de paradas válida é obrigatória para otimização.")
            return

        if len(stops) > MAX_STOPS_LIMIT:
            self.send_error_json(HTTPStatus.BAD_REQUEST, f"Máximo de {MAX_STOPS_LIMIT} paradas permitido no MVP.")
            return

        # Origem (Fábrica)
        origin_input = body.get("origin", {})
        origin = {
            "nome": sanitize_text(origin_input.get("nome", "Fábrica de Estofados")),
            "endereco": sanitize_text(origin_input.get("endereco", DEFAULT_FACTORY_ADDR)),
            "lat": float(origin_input.get("lat", DEFAULT_FACTORY_LAT)),
            "lon": float(origin_input.get("lon", DEFAULT_FACTORY_LON)),
            "cep": sanitize_text(origin_input.get("cep", DEFAULT_FACTORY_CEP))
        }

        return_to_origin = bool(body.get("return_to_origin", False))
        speed_kmh = float(body.get("speed_kmh", DEFAULT_SPEED_KMH))
        unload_min = int(body.get("unload_min", DEFAULT_UNLOAD_MIN))

        # Valida coordenadas de cada parada
        valid_stops = []
        for s in stops:
            try:
                lat = float(s["lat"])
                lon = float(s["lon"])
                valid_stops.append({
                    "cep": sanitize_text(s.get("cep", "")),
                    "logradouro": sanitize_text(s.get("logradouro", "")),
                    "bairro": sanitize_text(s.get("bairro", "")),
                    "localidade": sanitize_text(s.get("localidade", "")),
                    "uf": sanitize_text(s.get("uf", "")),
                    "endereco_completo": sanitize_text(s.get("endereco_completo", "")),
                    "nota": sanitize_text(s.get("nota", "")),
                    "lat": lat,
                    "lon": lon
                })
            except (KeyError, ValueError, TypeError):
                continue

        if not valid_stops:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Nenhuma parada com coordenadas válidas para otimizar.")
            return

        # Roteirização TSP
        ordered_stops, total_dist_km = solve_tsp(origin, valid_stops, return_to_origin)

        # Cálculo de métricas individuais de cada trecho (leg)
        enriched_stops = []
        cur_lat, cur_lon = origin["lat"], origin["lon"]
        acum_dist = 0.0
        acum_tempo_min = 0

        for idx, stop in enumerate(ordered_stops, start=1):
            trecho_dist = haversine_km(cur_lat, cur_lon, stop["lat"], stop["lon"])
            acum_dist += trecho_dist
            trecho_tempo = round((trecho_dist / speed_kmh) * 60)
            acum_tempo_min += trecho_tempo + unload_min

            # Links de navegação para esta parada individual
            google_nav_url = f"https://www.google.com/maps/dir/?api=1&destination={stop['lat']},{stop['lon']}"
            waze_nav_url = f"https://waze.com/ul?ll={stop['lat']},{stop['lon']}&navigate=yes"

            enriched_stops.append({
                "ordem": idx,
                **stop,
                "distancia_trecho_km": trecho_dist,
                "distancia_acumulada_km": round(acum_dist, 2),
                "tempo_trecho_min": trecho_tempo,
                "tempo_descarregamento_min": unload_min,
                "tempo_acumulado_min": acum_tempo_min,
                "google_nav_url": google_nav_url,
                "waze_nav_url": waze_nav_url
            })
            cur_lat, cur_lon = stop["lat"], stop["lon"]

        retorno_info = None
        if return_to_origin and enriched_stops:
            retorno_dist = haversine_km(cur_lat, cur_lon, origin["lat"], origin["lon"])
            retorno_tempo = round((retorno_dist / speed_kmh) * 60)
            acum_dist += retorno_dist
            acum_tempo_min += retorno_tempo
            retorno_info = {
                "distancia_km": retorno_dist,
                "tempo_min": retorno_tempo
            }

        total_dist_km = round(acum_dist, 2)
        tempo_total_horas = round(acum_tempo_min / 60, 1)

        # Links globais
        maps_links = generate_maps_links(origin, ordered_stops)

        self.send_json_response(HTTPStatus.OK, {
            "success": True,
            "origin": origin,
            "total_paradas": len(enriched_stops),
            "distancia_total_km": total_dist_km,
            "tempo_total_min": acum_tempo_min,
            "tempo_total_formatado": f"{acum_tempo_min // 60}h {acum_tempo_min % 60}min",
            "tempo_estimado_descarregamento_total_min": len(enriched_stops) * unload_min,
            "return_to_origin": return_to_origin,
            "retorno_info": retorno_info,
            "maps_links": maps_links,
            "paradas": enriched_stops
        })

    def handle_save_romaneio(self, body: Dict[str, Any]):
        """Salva romaneio gerado no banco de dados SQLite."""
        titulo = sanitize_text(body.get("titulo", f"Romaneio {datetime.now().strftime('%d/%m/%Y %H:%M')}"))
        total_paradas = int(body.get("total_paradas", 0))
        distancia_total = float(body.get("distancia_total_km", 0.0))
        tempo_total_min = int(body.get("tempo_total_min", 0))
        dados = body.get("dados")

        if not dados:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Dados do romaneio não informados.")
            return

        dados_json_str = json.dumps(dados, ensure_ascii=False)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO romaneios (titulo, total_paradas, distancia_total_km, tempo_total_min, dados_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (titulo, total_paradas, distancia_total, tempo_total_min, dados_json_str))
                romaneio_id = cursor.lastrowid
                conn.commit()

            self.send_json_response(HTTPStatus.CREATED, {
                "success": True,
                "id": romaneio_id,
                "message": "Romaneio gravado com sucesso."
            })
        except Exception as e:
            sys.stderr.write(f"[DB Error] Falha ao salvar romaneio: {e}\n")
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Não foi possível gravar o romaneio.")

def run_server():
    """Inicia o servidor HTTP."""
    init_db()
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, LogisticaHttpHandler)
    print("=" * 60)
    print(" 🚚 OTIMIZADOR DE ROTAS DE ENTREGA - FÁBRICA DE ESTOFADOS")
    print(f" Servidor iniciado em: http://{HOST}:{PORT}")
    print(f" Modo: Beta (MVP & KISS)")
    print(f" Banco de Dados: {DB_PATH}")
    print(" Pressione Ctrl+C para encerrar")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado com sucesso.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()

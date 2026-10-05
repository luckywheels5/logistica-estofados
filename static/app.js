/**
 * App Frontend - Otimizador de Rotas de Entrega (Estofados)
 * Metodologia MVP & KISS (Beta)
 * Suporta 100% Execução Estática (GitHub Pages) e Execução com Backend Local
 */

document.addEventListener("DOMContentLoaded", () => {
  // Estado da Aplicação
  const state = {
    factory: {
      nome: "Fábrica de Estofados - Sumaré",
      cep: "13170-023",
      endereco: "Av. Rebouças, Centro, Sumaré - SP",
      lat: -22.82194,
      lon: -47.26694
    },
    validatedStops: [],
    currentRomaneio: null,
    map: null,
    mapLayerGroup: null,
    cacheCep: new Map()
  };

  // Elementos do DOM
  const elements = {
    factoryCep: document.getElementById("factoryCep"),
    btnUpdateFactory: document.getElementById("btnUpdateFactory"),
    factoryAddressInfo: document.getElementById("factoryAddressInfo"),
    chkReturnFactory: document.getElementById("chkReturnFactory"),
    unloadTime: document.getElementById("unloadTime"),
    cepsInput: document.getElementById("cepsInput"),
    inputCountFeedback: document.getElementById("inputCountFeedback"),
    btnLoadExample: document.getElementById("btnLoadExample"),
    btnClearInput: document.getElementById("btnClearInput"),
    btnGeocode: document.getElementById("btnGeocode"),
    alertBox: document.getElementById("alertBox"),
    alertContent: document.getElementById("alertContent"),
    sectionValidated: document.getElementById("sectionValidated"),
    validCount: document.getElementById("validCount"),
    tbodyValidated: document.getElementById("tbodyValidated"),
    btnOptimize: document.getElementById("btnOptimize"),
    sectionResults: document.getElementById("sectionResults"),
    metricStops: document.getElementById("metricStops"),
    metricDistance: document.getElementById("metricDistance"),
    metricTime: document.getElementById("metricTime"),
    btnOpenFullMaps: document.getElementById("btnOpenFullMaps"),
    btnCopyWhatsApp: document.getElementById("btnCopyWhatsApp"),
    btnPrintRomaneio: document.getElementById("btnPrintRomaneio"),
    btnSaveHistory: document.getElementById("btnSaveHistory"),
    stopsTimeline: document.getElementById("stopsTimeline"),
    romaneioTimestamp: document.getElementById("romaneioTimestamp"),
    romaneioOrigemLabel: document.getElementById("romaneioOrigemLabel"),
    historyList: document.getElementById("historyList"),
    btnRefreshHistory: document.getElementById("btnRefreshHistory"),
    toast: document.getElementById("toast")
  };

  // Exemplos reais da Região Metropolitana de Campinas (especificação do projeto)
  const EXAMPLE_INPUT = 
`13170-023 - Sofá Retrátil 3 Lugares Suede Cinza (Sumaré)
13380-001 - Estofado de Canto Linho Bege (Nova Odessa)
13450-029 - Sofá Cama 2 Lugares Veludo Azul (Santa Bárbara d'Oeste)
13010-001 - Conjunto Estofado 3 e 2 Lugares (Campinas Centro)
13400-015 - Poltrona Giratória e Puff (Piracicaba)`;

  // --- FUNÇÕES UTILITÁRIAS ---

  function showToast(message, duration = 3000) {
    if (!elements.toast) return;
    elements.toast.textContent = message;
    elements.toast.classList.remove("hidden");
    setTimeout(() => {
      elements.toast.classList.add("hidden");
    }, duration);
  }

  function showAlert(errors) {
    if (!errors || errors.length === 0) {
      elements.alertBox.classList.add("hidden");
      elements.alertContent.innerHTML = "";
      return;
    }
    let html = "<strong>Atenção aos seguintes itens informados:</strong><ul>";
    errors.forEach(err => {
      html += `<li><strong>${escapeHtml(err.raw || "Item")}:</strong> ${escapeHtml(err.error || "Inválido")}</li>`;
    });
    html += "</ul>";
    elements.alertContent.innerHTML = html;
    elements.alertBox.classList.remove("hidden");
  }

  function hideAlert() {
    elements.alertBox.classList.add("hidden");
    elements.alertContent.innerHTML = "";
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function sanitizeCep(raw) {
    if (!raw) return null;
    const digits = String(raw).replace(/\D/g, "");
    return digits.length === 8 ? digits : null;
  }

  function updateLineCount() {
    const lines = elements.cepsInput.value.split("\n").filter(l => l.trim().length > 0);
    elements.inputCountFeedback.textContent = `${lines.length} linha${lines.length === 1 ? "" : "s"} detectada${lines.length === 1 ? "" : "s"}`;
  }

  // --- MATEMÁTICA DE ROTA (HAVERSINE & TSP 2-OPT) ---

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371.0;
    const toRad = deg => (deg * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Number((R * c * 1.30).toFixed(2)); // Fator de correção rodoviário
  }

  function solveTsp(origin, stops, returnToOrigin = false) {
    if (!stops || stops.length === 0) return { ordered: [], totalDist: 0 };
    if (stops.length === 1) {
      let d = haversineKm(origin.lat, origin.lon, stops[0].lat, stops[0].lon);
      if (returnToOrigin) {
        d += haversineKm(stops[0].lat, stops[0].lon, origin.lat, origin.lon);
      }
      return { ordered: stops, totalDist: Number(d.toFixed(2)) };
    }

    // 1. Heurística Gulosa do Vizinho Mais Próximo (Nearest Neighbor)
    const unvisited = [...stops];
    const ordered = [];
    let curLat = origin.lat;
    let curLon = origin.lon;

    while (unvisited.length > 0) {
      let bestIdx = 0;
      let bestDist = Infinity;
      for (let i = 0; i < unvisited.length; i++) {
        const d = haversineKm(curLat, curLon, unvisited[i].lat, unvisited[i].lon);
        if (d < bestDist) {
          bestDist = d;
          bestIdx = i;
        }
      }
      const nextStop = unvisited.splice(bestIdx, 1)[0];
      ordered.push(nextStop);
      curLat = nextStop.lat;
      curLon = nextStop.lon;
    }

    // 2. Otimização 2-Opt (Desata cruzamentos de rotas)
    function calcTotal(tour) {
      let tot = haversineKm(origin.lat, origin.lon, tour[0].lat, tour[0].lon);
      for (let i = 0; i < tour.length - 1; i++) {
        tot += haversineKm(tour[i].lat, tour[i].lon, tour[i + 1].lat, tour[i + 1].lon);
      }
      if (returnToOrigin) {
        tot += haversineKm(tour[tour.length - 1].lat, tour[tour.length - 1].lon, origin.lat, origin.lon);
      }
      return tot;
    }

    let bestTour = [...ordered];
    let bestDist = calcTotal(bestTour);
    let improved = true;
    let iterations = 0;

    while (improved && iterations < 50) {
      improved = false;
      iterations++;
      for (let i = 0; i < bestTour.length - 1; i++) {
        for (let j = i + 1; j < bestTour.length; j++) {
          const candidate = [
            ...bestTour.slice(0, i),
            ...bestTour.slice(i, j + 1).reverse(),
            ...bestTour.slice(j + 1)
          ];
          const candDist = calcTotal(candidate);
          if (candDist < bestDist - 0.05) {
            bestTour = candidate;
            bestDist = candDist;
            improved = true;
            break;
          }
        }
        if (improved) break;
      }
    }

    return { ordered: bestTour, totalDist: Number(bestDist.toFixed(2)) };
  }

  // --- GEOCODIFICAÇÃO (CLIENT-SIDE & CORS) ---

  async function fetchWithTimeout(url, timeoutMs = 4500) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(id);
      if (!response.ok) return null;
      return await response.json();
    } catch {
      clearTimeout(id);
      return null;
    }
  }

  async function geocodeSingleCep(cepDigits) {
    if (state.cacheCep.has(cepDigits)) {
      return state.cacheCep.get(cepDigits);
    }

    let res = {
      cep: `${cepDigits.slice(0, 5)}-${cepDigits.slice(5)}`,
      logradouro: "",
      bairro: "",
      localidade: "",
      uf: "",
      lat: null,
      lon: null
    };

    // 1. BrasilAPI v2 (Retorna logradouro, bairro, cidade e coordenadas diretas)
    const bApi = await fetchWithTimeout(`https://brasilapi.com.br/api/cep/v2/${cepDigits}`);
    if (bApi && !bApi.errors && bApi.city) {
      res.logradouro = bApi.street || "";
      res.bairro = bApi.neighborhood || "";
      res.localidade = bApi.city || "";
      res.uf = bApi.state || "";
      if (bApi.location && bApi.location.coordinates) {
        const c = bApi.location.coordinates;
        if (c.latitude && c.longitude) {
          res.lat = parseFloat(c.latitude);
          res.lon = parseFloat(c.longitude);
        }
      }
    }

    // 2. ViaCEP (Fallback para endereço oficial se BrasilAPI falhar)
    if (!res.localidade) {
      const vCep = await fetchWithTimeout(`https://viacep.com.br/ws/${cepDigits}/json/`);
      if (vCep && !vCep.erro) {
        res.logradouro = vCep.logradouro || "";
        res.bairro = vCep.bairro || "";
        res.localidade = vCep.localidade || "";
        res.uf = vCep.uf || "";
      }
    }

    // 3. OpenStreetMap Nominatim se faltar latitude/longitude
    if (res.localidade && res.lat === null) {
      const addrQuery = encodeURIComponent(`${res.logradouro}, ${res.bairro}, ${res.localidade}, ${res.uf}, Brasil`);
      const nom = await fetchWithTimeout(`https://nominatim.openstreetmap.org/search?q=${addrQuery}&format=json&limit=1&countrycodes=br`);
      if (Array.isArray(nom) && nom.length > 0) {
        res.lat = parseFloat(nom[0].lat);
        res.lon = parseFloat(nom[0].lon);
      } else {
        // Fallback centro do município
        const cityQuery = encodeURIComponent(`${res.localidade}, ${res.uf}, Brasil`);
        const nomCity = await fetchWithTimeout(`https://nominatim.openstreetmap.org/search?q=${cityQuery}&format=json&limit=1&countrycodes=br`);
        if (Array.isArray(nomCity) && nomCity.length > 0) {
          res.lat = parseFloat(nomCity[0].lat);
          res.lon = parseFloat(nomCity[0].lon);
        }
      }
    }

    if (res.localidade && res.lat !== null) {
      res.endereco_completo = `${res.logradouro}, ${res.bairro}, ${res.localidade} - ${res.uf}`.replace(/^[\s,]+|[\s,]+$/g, "");
      state.cacheCep.set(cepDigits, res);
      return res;
    }

    return null;
  }

  // --- ATUALIZAÇÃO DA FÁBRICA ---

  async function handleUpdateFactory() {
    const rawCep = elements.factoryCep.value.trim();
    const cepDigits = sanitizeCep(rawCep);
    if (!cepDigits) {
      showToast("Informe um CEP válido com 8 dígitos para a fábrica.");
      return;
    }

    elements.btnUpdateFactory.disabled = true;
    elements.btnUpdateFactory.textContent = "Buscando...";

    try {
      const geo = await geocodeSingleCep(cepDigits);
      if (geo && geo.lat !== null) {
        state.factory = {
          nome: "Fábrica de Estofados",
          cep: geo.cep,
          endereco: geo.endereco_completo,
          lat: geo.lat,
          lon: geo.lon
        };
        elements.factoryAddressInfo.innerHTML = `<strong>Fábrica Atualizada:</strong> ${escapeHtml(geo.endereco_completo)}`;
        elements.romaneioOrigemLabel.textContent = `${geo.localidade} - ${geo.uf}`;
        showToast("Ponto de partida da fábrica atualizado!");
      } else {
        showToast("Não foi possível localizar as coordenadas da fábrica para este CEP.");
      }
    } catch {
      showToast("Erro ao buscar CEP da fábrica.");
    } finally {
      elements.btnUpdateFactory.disabled = false;
      elements.btnUpdateFactory.textContent = "Atualizar Fábrica";
    }
  }

  // --- GEOCODIFICAÇÃO DE CEPS ---

  async function handleGeocode() {
    hideAlert();
    const rawText = elements.cepsInput.value.trim();
    if (!rawText) {
      showAlert([{ raw: "Entrada vazia", error: "Cole ou digite ao menos um CEP para continuar." }]);
      return;
    }

    const lines = rawText.split("\n").map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length === 0) {
      showAlert([{ raw: "Entrada vazia", error: "Nenhum CEP encontrado." }]);
      return;
    }

    elements.btnGeocode.disabled = true;
    elements.btnGeocode.textContent = "⏳ Geocodificando CEPs...";

    const validItems = [];
    const invalidItems = [];

    for (const line of lines) {
      const cepDigits = sanitizeCep(line);
      let nota = "";
      const matchNote = line.match(/(\d{5}-?\d{3})\s*[-–:]?\s*(.+)/);
      if (matchNote) {
        nota = matchNote[2].trim().slice(0, 80);
      }

      if (!cepDigits) {
        invalidItems.push({ raw: line, error: "CEP com formato inválido (deve conter 8 dígitos)" });
        continue;
      }

      const geo = await geocodeSingleCep(cepDigits);
      if (!geo || geo.lat === null) {
        invalidItems.push({ raw: line, error: "Endereço ou coordenadas não localizados para este CEP" });
      } else {
        validItems.push({
          ...geo,
          nota: nota || "Estofado"
        });
      }
    }

    if (invalidItems.length > 0) {
      showAlert(invalidItems);
    }

    state.validatedStops = validItems;
    renderValidatedTable(validItems);

    if (validItems.length > 0) {
      elements.sectionValidated.classList.remove("hidden");
      elements.sectionValidated.scrollIntoView({ behavior: "smooth", block: "start" });
      showToast(`${validItems.length} paradas identificadas com sucesso!`);
    } else {
      elements.sectionValidated.classList.add("hidden");
    }

    elements.btnGeocode.disabled = false;
    elements.btnGeocode.textContent = "🔍 1. Validar & Geocodificar CEPs";
  }

  function renderValidatedTable(stops) {
    elements.validCount.textContent = stops.length;
    elements.tbodyValidated.innerHTML = "";

    stops.forEach((stop, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${idx + 1}</strong></td>
        <td><span class="tag-cep">${escapeHtml(stop.cep)}</span></td>
        <td>${escapeHtml(stop.logradouro || "-")} <small style="color:#64748b;">(${escapeHtml(stop.bairro || "")})</small></td>
        <td>${escapeHtml(stop.localidade)} - ${escapeHtml(stop.uf)}</td>
        <td>${escapeHtml(stop.nota || "Estofado")}</td>
        <td><span class="tag-status-ok">✓ Localizado</span></td>
      `;
      elements.tbodyValidated.appendChild(tr);
    });
  }

  // --- OTIMIZAÇÃO DE ROTA (TSP) ---

  function handleOptimize() {
    if (!state.validatedStops || state.validatedStops.length === 0) {
      showToast("Nenhuma parada válida para otimizar.");
      return;
    }

    elements.btnOptimize.disabled = true;
    elements.btnOptimize.textContent = "⚡ Calculando Melhor Rota...";

    const returnToOrigin = elements.chkReturnFactory.checked;
    const unloadMin = parseInt(elements.unloadTime.value, 10) || 20;
    const speedKmh = 45.0;

    const { ordered, totalDist } = solveTsp(state.factory, state.validatedStops, returnToOrigin);

    // Enriquecimento com distâncias por trecho e tempos
    let curLat = state.factory.lat;
    let curLon = state.factory.lon;
    let acumDist = 0;
    let acumTempoMin = 0;

    const enrichedStops = ordered.map((stop, idx) => {
      const trechoDist = haversineKm(curLat, curLon, stop.lat, stop.lon);
      acumDist += trechoDist;
      const trechoTempo = Math.round((trechoDist / speedKmh) * 60);
      acumTempoMin += trechoTempo + unloadMin;

      const googleNavUrl = `https://www.google.com/maps/dir/?api=1&destination=${stop.lat},${stop.lon}`;
      const wazeNavUrl = `https://waze.com/ul?ll=${stop.lat},${stop.lon}&navigate=yes`;

      curLat = stop.lat;
      curLon = stop.lon;

      return {
        ordem: idx + 1,
        ...stop,
        distancia_trecho_km: trechoDist,
        distancia_acumulada_km: Number(acumDist.toFixed(2)),
        tempo_trecho_min: trechoTempo,
        tempo_descarregamento_min: unloadMin,
        tempo_acumulado_min: acumTempoMin,
        google_nav_url: googleNavUrl,
        waze_nav_url: wazeNavUrl
      };
    });

    let retornoInfo = null;
    if (returnToOrigin && enrichedStops.length > 0) {
      const retDist = haversineKm(curLat, curLon, state.factory.lat, state.factory.lon);
      const retTempo = Math.round((retDist / speedKmh) * 60);
      acumDist += retDist;
      acumTempoMin += retTempo;
      retornoInfo = { distancia_km: retDist, tempo_min: retTempo };
    }

    // Link do Google Maps com Waypoints
    const originStr = `${state.factory.lat},${state.factory.lon}`;
    const destStop = enrichedStops[enrichedStops.length - 1];
    const destStr = `${destStop.lat},${destStop.lon}`;
    let waypointsStr = "";
    if (enrichedStops.length > 1) {
      waypointsStr = enrichedStops.slice(0, -1).map(s => `${s.lat},${s.lon}`).join("|");
    }

    const mapParams = new URLSearchParams({
      api: "1",
      origin: originStr,
      destination: destStr,
      travelmode: "driving"
    });
    if (waypointsStr) {
      mapParams.set("waypoints", waypointsStr);
    }
    const fullGoogleMaps = `https://www.google.com/maps/dir/?${mapParams.toString()}`;

    const romaneioData = {
      origin: state.factory,
      total_paradas: enrichedStops.length,
      distancia_total_km: Number(acumDist.toFixed(2)),
      tempo_total_min: acumTempoMin,
      tempo_total_formatado: `${Math.floor(acumTempoMin / 60)}h ${(acumTempoMin % 60).toString().padStart(2, "0")}min`,
      return_to_origin: returnToOrigin,
      retorno_info: retornoInfo,
      maps_links: { google_maps_full: fullGoogleMaps },
      paradas: enrichedStops
    };

    state.currentRomaneio = romaneioData;
    renderRomaneioResults(romaneioData);
    elements.sectionResults.classList.remove("hidden");
    elements.sectionResults.scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Rota otimizada calculada com sucesso!");

    elements.btnOptimize.disabled = false;
    elements.btnOptimize.textContent = "⚡ 2. Otimizar Rota de Entrega (Menor Distância)";
  }

  // --- RENDERIZAÇÃO DOS RESULTADOS ---

  function renderRomaneioResults(data) {
    elements.metricStops.textContent = data.total_paradas;
    elements.metricDistance.textContent = data.distancia_total_km;
    elements.metricTime.textContent = data.tempo_total_formatado;

    if (data.maps_links && data.maps_links.google_maps_full) {
      elements.btnOpenFullMaps.href = data.maps_links.google_maps_full;
      elements.btnOpenFullMaps.classList.remove("hidden");
    } else {
      elements.btnOpenFullMaps.classList.add("hidden");
    }

    const now = new Date();
    elements.romaneioTimestamp.textContent = `Gerado em: ${now.toLocaleDateString("pt-BR")} às ${now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
    elements.romaneioOrigemLabel.textContent = `${data.origin.nome} (${data.origin.endereco})`;

    renderTimeline(data);
    renderMap(data);
  }

  function renderTimeline(data) {
    elements.stopsTimeline.innerHTML = "";

    const factoryItem = document.createElement("div");
    factoryItem.className = "timeline-item";
    factoryItem.innerHTML = `
      <div class="timeline-badge badge-factory">🏭</div>
      <div class="timeline-content">
        <div class="timeline-header">
          <span class="stop-city">Ponto de Partida: ${escapeHtml(data.origin.nome)}</span>
          <span class="stop-dist">Saída</span>
        </div>
        <p class="stop-address">${escapeHtml(data.origin.endereco)} - CEP ${escapeHtml(data.origin.cep)}</p>
      </div>
    `;
    elements.stopsTimeline.appendChild(factoryItem);

    data.paradas.forEach(stop => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      item.innerHTML = `
        <div class="timeline-badge">${stop.ordem}</div>
        <div class="timeline-content">
          <div class="timeline-header">
            <span class="stop-city">#${stop.ordem} - ${escapeHtml(stop.localidade)} / ${escapeHtml(stop.uf)}</span>
            <span class="stop-dist">+${stop.distancia_trecho_km} km (~${stop.tempo_trecho_min} min)</span>
          </div>
          <p class="stop-address">
            <strong>${escapeHtml(stop.logradouro || "Endereço")}</strong>, ${escapeHtml(stop.bairro || "")} 
            &bull; CEP: <span class="tag-cep">${escapeHtml(stop.cep)}</span>
          </p>
          ${stop.nota ? `<div class="stop-note">🛋️ ${escapeHtml(stop.nota)}</div>` : ""}
          <div class="stop-actions print-hidden">
            <a href="${stop.google_nav_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-nav-google">
              🗺️ Google Maps
            </a>
            <a href="${stop.waze_nav_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-nav-waze">
              🚗 Waze
            </a>
          </div>
        </div>
      `;
      elements.stopsTimeline.appendChild(item);
    });

    if (data.return_to_origin && data.retorno_info) {
      const returnItem = document.createElement("div");
      returnItem.className = "timeline-item";
      returnItem.innerHTML = `
        <div class="timeline-badge badge-factory">🏁</div>
        <div class="timeline-content">
          <div class="timeline-header">
            <span class="stop-city">Retorno à Fábrica</span>
            <span class="stop-dist">+${data.retorno_info.distancia_km} km (~${data.retorno_info.tempo_min} min)</span>
          </div>
          <p class="stop-address">${escapeHtml(data.origin.nome)}</p>
        </div>
      `;
      elements.stopsTimeline.appendChild(returnItem);
    }
  }

  // --- MAPA INTERATIVO (LEAFLET) ---

  function initMapIfNeeded() {
    if (!state.map) {
      const mapEl = document.getElementById("routeMap");
      if (!mapEl) return;
      state.map = L.map(mapEl).setView([state.factory.lat, state.factory.lon], 11);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(state.map);
      state.mapLayerGroup = L.layerGroup().addTo(state.map);
    }
  }

  function renderMap(data) {
    initMapIfNeeded();
    if (!state.map || !state.mapLayerGroup) return;

    state.mapLayerGroup.clearLayers();
    const points = [];

    // Marcador da Fábrica
    const factoryIcon = L.divIcon({
      className: "custom-map-marker",
      html: `<div style="background-color:#1e293b; color:white; width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:18px; border:2px solid white; box-shadow:0 2px 5px rgba(0,0,0,0.4);">🏭</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });

    const factoryLatLng = [data.origin.lat, data.origin.lon];
    points.push(factoryLatLng);

    L.marker(factoryLatLng, { icon: factoryIcon })
      .bindPopup(`<strong>Origem: Fábrica de Estofados</strong><br>${escapeHtml(data.origin.endereco)}`)
      .addTo(state.mapLayerGroup);

    // Marcadores das Paradas
    data.paradas.forEach(stop => {
      const stopLatLng = [stop.lat, stop.lon];
      points.push(stopLatLng);

      const stopIcon = L.divIcon({
        className: "custom-map-marker",
        html: `<div style="background-color:#1e3a8a; color:white; width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:14px; border:2px solid white; box-shadow:0 2px 5px rgba(0,0,0,0.3);">${stop.ordem}</div>`,
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      });

      const popupHtml = `
        <div style="font-family:sans-serif; min-width:180px;">
          <h4 style="margin:0 0 4px 0; color:#1e3a8a;">#Parada ${stop.ordem} - ${escapeHtml(stop.localidade)}</h4>
          <p style="margin:0 0 4px 0; font-size:12px;">${escapeHtml(stop.endereco_completo)}</p>
          ${stop.nota ? `<p style="margin:0 0 6px 0; font-size:11px; color:#b45309; background:#fef3c7; padding:2px 4px; border-radius:3px;">🛋️ ${escapeHtml(stop.nota)}</p>` : ""}
          <div style="display:flex; gap:6px; margin-top:6px;">
            <a href="${stop.google_nav_url}" target="_blank" style="font-size:11px; background:#eff6ff; color:#1d4ed8; padding:4px 6px; border-radius:4px; text-decoration:none; border:1px solid #bfdbfe;">Google Maps</a>
            <a href="${stop.waze_nav_url}" target="_blank" style="font-size:11px; background:#f0fdf4; color:#15803d; padding:4px 6px; border-radius:4px; text-decoration:none; border:1px solid #bbf7d0;">Waze</a>
          </div>
        </div>
      `;

      L.marker(stopLatLng, { icon: stopIcon })
        .bindPopup(popupHtml)
        .addTo(state.mapLayerGroup);
    });

    if (data.return_to_origin) {
      points.push(factoryLatLng);
    }

    if (points.length > 1) {
      L.polyline(points, {
        color: "#1d4ed8",
        weight: 4,
        opacity: 0.8,
        dashArray: "6, 8"
      }).addTo(state.mapLayerGroup);

      state.map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
    }
  }

  // --- WHATSAPP & CLIPBOARD ---

  function handleCopyWhatsApp() {
    if (!state.currentRomaneio) {
      showToast("Gere uma rota primeiro.");
      return;
    }

    const d = state.currentRomaneio;
    const now = new Date();
    const dataStr = now.toLocaleDateString("pt-BR");
    const horaStr = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

    let msg = `🚚 *ROMANEIO DE ENTREGA - FÁBRICA DE ESTOFADOS*\n`;
    msg += `📅 *Data:* ${dataStr} às ${horaStr}\n`;
    msg += `🏭 *Partida:* ${d.origin.nome} (${d.origin.endereco})\n`;
    msg += `📦 *Total de Paradas:* ${d.total_paradas}\n`;
    msg += `🛣️ *Distância Estimada:* ${d.distancia_total_km} km | ⏱️ *Tempo:* ${d.tempo_total_formatado}\n`;
    msg += `\n*ITINERÁRIO SEQUENCIAL OTIMIZADO:*\n`;

    d.paradas.forEach(p => {
      msg += `\n${p.ordem}️⃣ *Parada ${p.ordem}: ${p.localidade} - ${p.uf}*\n`;
      msg += `📍 ${p.endereco_completo} (CEP: ${p.cep})\n`;
      if (p.nota) msg += `🛋️ *Item:* ${p.nota}\n`;
      msg += `🗺️ *Google Maps:* ${p.google_nav_url}\n`;
      msg += `🚗 *Waze:* ${p.waze_nav_url}\n`;
    });

    if (d.maps_links && d.maps_links.google_maps_full) {
      msg += `\n🌐 *ROTA COMPLETA NO GOOGLE MAPS:*\n${d.maps_links.google_maps_full}\n`;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(msg).then(() => {
        showToast("Romaneio copiado! Pronto para colar no WhatsApp.");
      }).catch(() => {
        promptCopyFallback(msg);
      });
    } else {
      promptCopyFallback(msg);
    }
  }

  function promptCopyFallback(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    showToast("Romaneio copiado para a área de transferência!");
  }

  // --- HISTÓRICO DE ROMANEIOS (LOCALSTORAGE & SERVIDOR) ---

  const STORAGE_KEY = "estofados_romaneios_historico_v1";

  function handleSaveHistory() {
    if (!state.currentRomaneio) {
      showToast("Gere uma rota antes de salvar.");
      return;
    }

    const savedItem = {
      id: Date.now(),
      titulo: `Romaneio ${state.currentRomaneio.total_paradas} Paradas - ${new Date().toLocaleDateString("pt-BR")}`,
      criado_em: new Date().toLocaleString("pt-BR"),
      total_paradas: state.currentRomaneio.total_paradas,
      distancia_total_km: state.currentRomaneio.distancia_total_km,
      dados: state.currentRomaneio
    };

    try {
      const past = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      past.unshift(savedItem);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(past.slice(0, 15)));
      showToast("Romaneio arquivado com sucesso!");
      loadHistory();
    } catch {
      showToast("Erro ao arquivar localmente.");
    }
  }

  function loadHistory() {
    try {
      const items = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (items.length === 0) {
        elements.historyList.innerHTML = `<p class="text-muted">Nenhum romaneio salvo ainda.</p>`;
        return;
      }

      elements.historyList.innerHTML = "";
      items.forEach(item => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.innerHTML = `
          <div>
            <strong>${escapeHtml(item.titulo)}</strong>
            <div style="font-size:0.8rem; color:#64748b;">
              ${escapeHtml(item.criado_em)} &bull; ${item.total_paradas} paradas &bull; ${item.distancia_total_km} km
            </div>
          </div>
          <button type="button" class="btn btn-sm btn-outline btn-load-past">
            Carregar Rota
          </button>
        `;
        elements.historyList.appendChild(div);

        div.querySelector(".btn-load-past").addEventListener("click", () => {
          state.currentRomaneio = item.dados;
          state.validatedStops = item.dados.paradas || [];
          renderRomaneioResults(item.dados);
          elements.sectionResults.classList.remove("hidden");
          elements.sectionResults.scrollIntoView({ behavior: "smooth" });
          showToast("Romaneio carregado do histórico!");
        });
      });
    } catch {
      // Ignora erro
    }
  }

  // --- LISTENERS ---

  elements.cepsInput.addEventListener("input", updateLineCount);

  elements.btnLoadExample.addEventListener("click", () => {
    elements.cepsInput.value = EXAMPLE_INPUT;
    updateLineCount();
    showToast("Exemplo com cidades da RMC carregado!");
  });

  elements.btnClearInput.addEventListener("click", () => {
    elements.cepsInput.value = "";
    updateLineCount();
    hideAlert();
    elements.sectionValidated.classList.add("hidden");
  });

  elements.btnUpdateFactory.addEventListener("click", handleUpdateFactory);
  elements.btnGeocode.addEventListener("click", handleGeocode);
  elements.btnOptimize.addEventListener("click", handleOptimize);
  elements.btnCopyWhatsApp.addEventListener("click", handleCopyWhatsApp);
  elements.btnPrintRomaneio.addEventListener("click", () => window.print());
  elements.btnSaveHistory.addEventListener("click", handleSaveHistory);
  elements.btnRefreshHistory.addEventListener("click", loadHistory);

  updateLineCount();
  loadHistory();
});

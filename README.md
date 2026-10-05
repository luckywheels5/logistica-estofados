# 🚚 Otimizador de Rotas de Entrega - Fábrica de Estofados (Versão Beta MVP)

> Aplicativo de logística e roteirização inteligente para romaneios de entrega de estofados, desenvolvido sob as metodologias **MVP (Minimum Viable Product)** e **KISS (Keep It Simple, Stupid)**.

🌐 **Acesse Online (GitHub Pages):** [https://luckywheels5.github.io/logistica-estofados/](https://luckywheels5.github.io/logistica-estofados/)

---

## 📌 1. Visão Geral
Construído para simplificar e automatizar a rotina de expedição da fábrica de estofados (atendendo cidades da RMC como Sumaré, Nova Odessa, Santa Bárbara d'Oeste, Americana, Campinas e Piracicaba, além de qualquer cidade do Brasil). 

Elimina a ordenação manual de entregas, calculando a sequência mais eficiente de paradas a partir da simples colagem dos CEPs do dia.

---

## 🚀 2. Funcionalidades Principais (MVP & KISS)

* **Ingestão Rápida Flexível:**
  * O operador pode colar múltiplos CEPs de uma vez (um por linha ou separados por vírgula).
  * Suporta observações ou número de pedido junto ao CEP (ex: `13010-001 - Sofá Retrátil 3 Lugares Suede`).
  * Botão de teste rápido com cidades da Região Metropolitana de Campinas (RMC).

* **Geocodificação Automática em Camadas:**
  * Validação imediata de formato de CEP (8 dígitos).
  * Integração com **BrasilAPI v2** (obtém logradouro, bairro, cidade, UF e coordenadas de latitude/longitude).
  * Fallback com **ViaCEP** e **OpenStreetMap Nominatim**.
  * Alertas visuais destacados caso algum CEP informado seja inválido ou não localizado.

* **Algoritmo de Roteirização Inteligente (TSP):**
  * Solução para o Problema do Caixeiro-Viajante via **Nearest Neighbor** com refinamento **2-Opt**.
  * Cálculo de distância terrestre geodésica (fórmula de Haversine com fator de correção rodoviário).
  * Estimativa realista de tempo de deslocamento + tempo configurável de descarga por estofado (padrão: 20 min).
  * Opção de rota aberta (termina no último cliente) ou circuito fechado (retorna à fábrica).

* **Saída e Integração com o Motorista:**
  * **Mapa Interativo (Leaflet.js):** Visualização dos pontos numerados (#1, #2, #3...) e traçado da rota.
  * **Link Rota Completa no Google Maps:** Abre o itinerário pronto com múltiplos waypoints para navegação contínua.
  * **Navegação Individual:** Botões diretos para abrir o Google Maps ou Waze para cada parada no smartphone.
  * **Copiar para WhatsApp:** Gera texto formatado com emojis e links pronto para colar no grupo da expedição.
  * **Impressão de Romaneio A4:** Formatação limpa via CSS print para impressão física na prancheta do motorista.
  * **Histórico de Romaneios:** Permite salvar e consultar romaneios gerados recentemente.

---

## 💻 3. Como Executar

### Opção A: Acesso Direto Web (Sem Instalar Nada)
Abra no navegador o link do GitHub Pages:
👉 **[https://luckywheels5.github.io/logistica-estofados/](https://luckywheels5.github.io/logistica-estofados/)**

### Opção B: Execução Local com Script
Basta executar no terminal:
```bash
./abrir_app.sh
```

### Opção C: Execução Local com Servidor Python (Zero Dependências)
```bash
python3 server.py
```
Acesse em: `http://localhost:8000`

### Opção D: Abrir diretamente o arquivo HTML
Você também pode simplesmente abrir o arquivo `index.html` em qualquer navegador web moderno.

---

## 🧪 4. Testes Automatizados
O projeto conta com bateria de testes unitários que cobrem a integridade dos algoritmos de roteirização, sanitização e segurança:

```bash
python3 tests/test_app.py
```

---

## 🛡️ 5. Linha de Base de Segurança e Conformidade

Este projeto atende rigorosamente a lista de verificação de segurança:
* **Proteção de API:** Nenhuma chave de API exposta ou embutida no código. Todas as integrações utilizam APIs públicas abertas (BrasilAPI, ViaCEP, OSM).
* **Segurança de .env:** Arquivos `.env` devidamente incluídos no `.gitignore`.
* **Sem Senhas no Código:** Zero credenciais hardcoded.
* **Validação do Servidor e Sanitização:** Validação de entradas (formato regex de CEP, escape contra XSS e injeção).
* **Prevenção de Injeção SQL:** Todas as operações no SQLite utilizam consultas parametrizadas com placeholders (`?`).
* **Rate Limiting:** Limitador de taxa ativo no backend por IP.
* **Proteção Path Traversal:** O servidor estático valida se o arquivo requisitado está restrito ao diretório seguro.
* **Mensagens de Erro Seguras:** Respostas de erro padronizadas sem vazamento de stack traces ou caminhos internos.
* **CORS Seguro:** Configurado para acesso estrito e seguro.

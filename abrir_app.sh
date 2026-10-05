#!/usr/bin/env bash
# ==============================================================================
# Script de Inicialização Rápida - Otimizador de Rotas de Entrega (Estofados)
# Versão Beta (MVP & KISS)
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

PORT=8000
HOST="127.0.0.1"
URL="http://$HOST:$PORT"

echo "=========================================================="
echo " 🛋️ Iniciando Otimizador de Rotas de Entrega (Beta MVP)"
echo "=========================================================="

# Verifica se a porta já está em uso
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 || ss -ltn "( sport = :$PORT )" | grep -q ":$PORT"; then
    echo "Servidor já está rodando em $URL"
else
    echo "Iniciando servidor Python..."
    python3 "$DIR/server.py" &
    SERVER_PID=$!
    sleep 1
fi

echo "Abrindo navegador no endereço: $URL"

if command -v xdg-open > /dev/null; then
    xdg-open "$URL" >/dev/null 2>&1 &
elif command -v google-chrome > /dev/null; then
    google-chrome "$URL" >/dev/null 2>&1 &
elif command -v firefox > /dev/null; then
    firefox "$URL" >/dev/null 2>&1 &
else
    echo "Navegador padrão não detectado automaticamente. Abra manualmente: $URL"
fi

echo "Pronto! O aplicativo está pronto para uso."

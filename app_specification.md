# Especificação do Aplicativo: Otimizador de Rotas de Entrega (Estofados)

## 1. Visão Geral do Projeto
Este documento detalha os requisitos funcionais e o fluxo de uso de um aplicativo voltado para o setor de logística de uma fábrica de estofados. O objetivo principal é automatizar o cálculo de romaneios de entrega, determinando a sequência mais rápida e eficiente para múltiplos destinos (ex: Sumaré, Santa Bárbara d'Oeste, Nova Odessa, Campinas e Piracicaba) a partir da inserção de CEPs.

---

## 2. Contexto e Problema
* **Cenário Atual:** A equipe de logística gasta tempo e quebra a cabeça tentando ordenar manualmente as entregas do dia para evitar deslocamentos redundantes e otimizar o tempo.
* **Solução Proposta:** Um sistema simplificado onde o operador insere rapidamente os dados de entrega para receber a rota otimizada sem esforço burocrático.

---

## 3. Requisitos Funcionais
* **Entrada de Dados (Ingestão Rápida):**
  * Uma interface limpa e direta.
  * Campo de texto flexível onde o operador pode colar ou inserir os CEPs dos locais de entrega do dia (ou via importação simples de pedidos).
* **Processamento e Otimização:**
  * Geocodificação automática dos CEPs para converter endereços em coordenadas geográficas (latitude e longitude).
  * Aplicação de algoritmo de roteirização (problema do caixeiro-viajante) para calcular a menor distância e o menor tempo de percurso entre a fábrica e os pontos.
* **Saída Prática:**
  * Exibição de uma lista numerada clara com a sequência exata em que as paradas devem ser realizadas.
  * Disponibilização de um link ou integração direta para iniciar a navegação passo a passo (como Google Maps ou Waze) no celular do motorista.
* **Validação e Tratamento de Erros:**
  * Mecanismo para alertar sobre CEPs inválidos ou incorretos antes do cálculo final da rota.

---

## 4. Fluxo de Uso do Operador
1. **Abertura do App:** O operador acessa a tela principal.
2. **Inserção dos Destinos:** O operador digita ou cola os CEPs das entregas do dia.
3. **Cálculo da Rota:** O sistema processa os dados considerando a região e a distância geográfica.
4. **Execução:** O operador visualiza a ordem ideal de entrega e clica para iniciar a navegação para a primeira parada.

---

## 5. Próximos Passos
* Definir como os pedidos chegam atualmente à operação (planilhas, papel ou WhatsApp) para avaliar se haverá necessidade de uma etapa prévia de cadastro de pedidos.
* Encaminhar esta especificação para a ferramenta de desenvolvimento (Antigravity) para a construção do código.
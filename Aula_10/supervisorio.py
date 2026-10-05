#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# SUPERVISORIO WEB - Bancadas 01 a 12 (Laboratorio 8 com MQTT)
#
# Como funciona:
#   1. O paho-mqtt assina os topicos das 12 bancadas e guarda o ultimo valor
#      de cada uma num dicionario.
#   2. O Flask entrega uma pagina HTML e uma rota /api/bancadas com esse
#      dicionario em JSON.
#   3. A pagina ja abre com as 12 bancadas em VERMELHO (sem conexao).
#      A cada 1 segundo ela pergunta a /api/bancadas e pinta de VERDE as
#      bancadas que estao conectadas.
#
# Este supervisorio so OBSERVA. Ele nao envia comando nenhum para as bancadas.
#
# Uso:
#   python supervisorio.py
#   Abra no navegador: http://localhost:5000
# =============================================================================

import json
import logging
import threading
import time

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string

# --- CONFIGURACAO (EDITE AQUI) ------------------------------------------------

BROKER_HOST = "35.172.192.195"     # IP do computador com o Mosquitto
BROKER_PORTA = 1883
PREFIXO = "fiap/pc"
NUMERO_DE_BANCADAS = 12
SEM_TELEMETRIA_S = 6          # 3 telemetrias (2 s cada) sem chegar = suspeito

# --- DADOS DAS BANCADAS -------------------------------------------------------

# Nomes: bancada01, bancada02, ..., bancada12
NOMES = ["bancada%02d" % n for n in range(1, NUMERO_DE_BANCADAS + 1)]

trava = threading.Lock()      # o paho e o Flask rodam em threads diferentes
broker_conectado = False
historico = []                # ultimas 15 mudancas (para a tabela da pagina)

bancadas = {}
for nome in NOMES:
    bancadas[nome] = {
        "status": "-",
        "estado": "-",
        "ultimo_cmd": "-",
        "interlocks": 0,
        "falhas": 0,
        "uptime_s": 0,
        "rssi": None,
        "visto_em": 0.0,          # time.time() da ultima mensagem
        "telemetria_em": 0.0,     # time.time() da ultima telemetria
    }


def registrar(nome, texto):
    historico.insert(0, {"hora": time.strftime("%H:%M:%S"), "bancada": nome, "texto": texto})
    del historico[15:]            # guarda so as 15 mais recentes


# --- MQTT ---------------------------------------------------------------------

def ao_conectar(cliente, userdata, flags, reason_code, properties):
    global broker_conectado
    if reason_code.is_failure:
        print("[MQTT] broker recusou a conexao: %s" % reason_code)
        return
    for nome in NOMES:
        cliente.subscribe("%s/%s/#" % (PREFIXO, nome))
    with trava:
        broker_conectado = True
    print("[MQTT] conectado em %s:%d, assinando %d bancadas"
          % (BROKER_HOST, BROKER_PORTA, len(NOMES)))


def ao_desconectar(cliente, userdata, flags, reason_code, properties):
    global broker_conectado
    with trava:
        broker_conectado = False
    print("[MQTT] desconectado do broker")


def ao_receber(cliente, userdata, msg):
    # Topico chega como: fiap/pc/bancada03/estado
    partes = msg.topic.split("/")
    if len(partes) != 4:
        return
    nome = partes[2]
    campo = partes[3]
    if nome not in bancadas:
        return

    texto = msg.payload.decode("utf-8", errors="replace")
    agora = time.time()

    with trava:
        b = bancadas[nome]
        b["visto_em"] = agora

        if campo == "status":
            if texto != b["status"]:
                if texto == "online":
                    registrar(nome, "conectou")
                else:
                    registrar(nome, "desconectou")
            b["status"] = texto

        elif campo == "estado":
            if texto != b["estado"] and b["estado"] != "-":
                registrar(nome, "%s -> %s" % (b["estado"], texto))
            b["estado"] = texto

        elif campo == "telemetria":
            try:
                dados = json.loads(texto)
            except ValueError:
                print("[MQTT] telemetria invalida de %s: %s" % (nome, texto))
                return
            for chave in ("estado", "ultimo_cmd", "interlocks", "falhas", "uptime_s", "rssi"):
                if chave in dados:
                    b[chave] = dados[chave]
            b["telemetria_em"] = agora


def iniciar_mqtt():
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id="supervisorio-%d" % int(time.time()))
    cliente.on_connect = ao_conectar
    cliente.on_disconnect = ao_desconectar
    cliente.on_message = ao_receber
    cliente.reconnect_delay_set(min_delay=1, max_delay=5)
    cliente.connect_async(BROKER_HOST, BROKER_PORTA, keepalive=10)
    cliente.loop_start()          # roda o MQTT numa thread separada
    return cliente


# --- CONEXAO DE CADA BANCADA -------------------------------------------------

def esta_conectada(b, agora, conectado):
    """
    A bancada esta COM CONEXAO quando as tres coisas sao verdade:
      1. o supervisorio esta conectado ao broker;
      2. o ESP32 disse "online" (e o broker nao publicou o Last Will "offline");
      3. chegou telemetria dela nos ultimos SEM_TELEMETRIA_S segundos.
    Qualquer outra coisa e SEM CONEXAO.
    """
    if not conectado:
        return False
    if b["status"] != "online":
        return False
    return (agora - b["telemetria_em"]) <= SEM_TELEMETRIA_S


# --- FLASK --------------------------------------------------------------------

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)   # nao loga cada GET no terminal


@app.route("/")
def pagina():
    # As 12 bancadas ja vao desenhadas no HTML, antes de qualquer dado chegar.
    return render_template_string(PAGINA, titulo="Supervisório – Chão de Fábrica",
                                  nomes=NOMES)


@app.route("/api/bancadas")
def api_bancadas():
    agora = time.time()
    with trava:
        lista = []
        for nome in NOMES:
            b = dict(bancadas[nome])
            b["nome"] = nome
            b["conectada"] = esta_conectada(b, agora, broker_conectado)
            b["ja_comunicou"] = b["visto_em"] > 0
            b["visto_ha_s"] = None
            if b["visto_em"] > 0:
                b["visto_ha_s"] = round(agora - b["visto_em"], 1)
            lista.append(b)
        resposta = {
            "broker": broker_conectado,
            "broker_host": BROKER_HOST,
            "bancadas": lista,
            "historico": list(historico),
        }
    return jsonify(resposta)


# --- PAGINA HTML --------------------------------------------------------------

PAGINA = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }}</title>
<style>
  body   { margin: 0; font-family: Arial, sans-serif; background: #1f2428; color: #eee; }
  header { padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
  h1     { margin: 0; font-size: 22px; }
  #broker { padding: 6px 12px; border-radius: 6px; font-size: 14px; }

  #resumo { display: flex; gap: 12px; padding: 0 24px 12px; }
  .contador { border-radius: 8px; padding: 10px 16px; min-width: 140px; }
  .contador b { display: block; font-size: 28px; }

  #grade { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
           gap: 14px; padding: 0 24px 24px; }
  .card  { background: #2b3136; border-radius: 10px; overflow: hidden; }
  .topo  { padding: 10px 14px; font-weight: bold; display: flex; justify-content: space-between; }
  .corpo { padding: 10px 14px; font-size: 14px; line-height: 1.7; }
  .conexao { font-size: 20px; font-weight: bold; margin-bottom: 4px; }

  .com { background: #2e9e4f; }      /* verde: com conexao */
  .sem { background: #d7263d; }      /* vermelho: sem conexao */

  table { width: calc(100% - 48px); margin: 0 24px 24px; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #3a4046; }
  th { color: #9ca3af; }
</style>
</head>
<body>

<header>
  <h1>{{ titulo }}</h1>
  <span id="broker" class="sem">broker: aguardando...</span>
</header>

<div id="resumo">
  <div class="contador com"><b id="n-com">0</b>COM CONEXÃO</div>
  <div class="contador sem"><b id="n-sem">{{ nomes|length }}</b>SEM CONEXÃO</div>
</div>

<!-- As 12 bancadas ja nascem na tela, em vermelho -->
<div id="grade">
  {% for nome in nomes %}
  <div class="card" id="{{ nome }}">
    <div class="topo sem"><span>{{ nome }}</span><span class="visto">-</span></div>
    <div class="corpo">
      <div class="conexao">SEM CONEXÃO</div>
      Máquina: <b class="estado">-</b><br>
      Último comando do PC: <b class="cmd">-</b><br>
      Interlocks: <b class="interlocks">-</b> &nbsp; Falhas: <b class="falhas">-</b><br>
      Ligada há: <b class="uptime">-</b> &nbsp; Wi-Fi: <b class="rssi">-</b>
    </div>
  </div>
  {% endfor %}
</div>

<table>
  <thead><tr><th>Hora</th><th>Bancada</th><th>O que aconteceu</th></tr></thead>
  <tbody id="historico"></tbody>
</table>

<script>
// Escreve um texto dentro do cartao da bancada
function escrever(card, classe, valor) {
  card.querySelector("." + classe).textContent = valor;
}

// Atualiza UM cartao que ja existe na tela
function atualizarCard(b) {
  const card = document.getElementById(b.nome);
  if (card === null) {
    return;
  }

  if (b.conectada) {
    card.querySelector(".topo").className = "topo com";
    escrever(card, "conexao", "COM CONEXÃO");
  } else {
    card.querySelector(".topo").className = "topo sem";
    escrever(card, "conexao", "SEM CONEXÃO");
  }

  if (b.visto_ha_s === null) {
    escrever(card, "visto", "-");
  } else {
    escrever(card, "visto", "há " + b.visto_ha_s + " s");
  }

  // Bancada que nunca mandou nada: deixa os tracos
  if (!b.ja_comunicou) {
    return;
  }
  escrever(card, "estado", b.estado);
  escrever(card, "cmd", b.ultimo_cmd);
  escrever(card, "interlocks", b.interlocks);
  escrever(card, "falhas", b.falhas);
  escrever(card, "uptime", b.uptime_s + " s");
  if (b.rssi === null) {
    escrever(card, "rssi", "-");
  } else {
    escrever(card, "rssi", b.rssi + " dBm");
  }
}

function atualizarResumo(lista) {
  const com = lista.filter(b => b.conectada).length;
  document.getElementById("n-com").textContent = com;
  document.getElementById("n-sem").textContent = lista.length - com;
}

// Se o proprio supervisorio cair, todos os cartoes ficam vermelhos
function tudoSemConexao() {
  const lista = [];
  for (const card of document.querySelectorAll(".card")) {
    lista.push({ nome: card.id, conectada: false, visto_ha_s: null, ja_comunicou: false });
  }
  for (const b of lista) {
    atualizarCard(b);
  }
  atualizarResumo(lista);
}

async function atualizar() {
  const broker = document.getElementById("broker");
  try {
    const resposta = await fetch("/api/bancadas");
    const dados = await resposta.json();

    if (dados.broker) {
      broker.textContent = "broker " + dados.broker_host + " conectado";
      broker.className = "com";
    } else {
      broker.textContent = "broker " + dados.broker_host + " DESCONECTADO";
      broker.className = "sem";
    }

    for (const b of dados.bancadas) {
      atualizarCard(b);
    }
    atualizarResumo(dados.bancadas);
    document.getElementById("historico").innerHTML = dados.historico.map(
      h => `<tr><td>${h.hora}</td><td>${h.bancada}</td><td>${h.texto}</td></tr>`
    ).join("");
  } catch (erro) {
    broker.textContent = "supervisório fora do ar";
    broker.className = "sem";
    tudoSemConexao();
  }
}

atualizar();
setInterval(atualizar, 1000);
</script>
</body>
</html>
"""


# --- PRINCIPAL ----------------------------------------------------------------

if __name__ == "__main__":
    iniciar_mqtt()
    # use_reloader=False: com o reloader ligado o Flask roda este arquivo duas
    # vezes e abriria duas conexoes MQTT com o broker.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
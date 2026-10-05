/*
 * =============================================================================
 * Aula_08_MQTT.ino
 * Laboratorio 8 (Area de Seguranca) + publicacao dos dados no broker MQTT.
 * Placa: ESP32 Dev Module | Arduino IDE | Biblioteca: PubSubClient (Nick O'Leary)
 *
 * O LADO PYTHON (Aula_08.py) NAO MUDA. O protocolo serial e o mesmo:
 *   'S' = libera     'D' = trava     qualquer outro byte e ignorado
 *   O Python reenvia o estado a cada ~100 ms (heartbeat).
 *   WATCHDOG: 300 ms sem byte valido -> FALHA.
 *   REARME:   saindo de FALHA, so volta com link valido + botao de rearme.
 *
 * ARQUITETURA:
 *   nucleo 1 - loop(): serial, watchdog, maquina de estados, LEDs, buzzer.
 *              Mesma logica do Aula_08.ino. Nunca chama nada de rede.
 *   nucleo 0 - tarefaMqtt(): Wi-Fi, conexao ao broker, publicacao.
 *              Pode bloquear por segundos sem afetar o interlock.
 *   nucleo 1 -> nucleo 0: fila de eventos com timeout zero.
 *
 * TOPICOS (BASE = "fiap/pc/<BANCADA>"), todos publicados pelo ESP32:
 *   BASE/status      "online" | "offline"          retido, Last Will = "offline"
 *   BASE/estado      LIBERADO | BLOQUEADO | FALHA  retido
 *   BASE/evento      JSON a cada transicao, com a causa
 *   BASE/telemetria  JSON a cada 2 s
 *
 * O ESP32 publica o que ELE sabe: estado, comandos recebidos do PC, rearmes,
 * quedas de link. Posicao da mao, d/R, v e a saida da MLP ficam no PC e nao
 * chegam aqui, porque o protocolo serial carrega so 'S' ou 'D'.
 *
 * Perder o broker NAO para nem libera a maquina: MQTT e so supervisao.
 *
 * LEDS (sempre um so aceso):
 *   verde = LIBERADO   vermelho = BLOQUEADO   amarelo = FALHA / aguardando rearme
 * BUZZER: 1 pulso = rearme / 'S' recebido   2 pulsos = 'D' recebido
 *
 * AVISO: demonstracao didatica, nao e dispositivo de seguranca.
 * =============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>

// --- CONFIGURACAO DE REDE (EDITE AQUI) ---------------------------------------
const char*    WIFI_SSID   = "LAB_IOT";
const char*    WIFI_SENHA  = "trocar_senha";
const char*    MQTT_HOST   = "192.168.0.10";   // IP do computador com o Mosquitto
const uint16_t MQTT_PORTA  = 1883;
const char*    BANCADA     = "bancada01";      // UNICO na sala
const char*    PREFIXO     = "fiap/pc";

// --- PINOS --------------------------------------------------------------------
const int PINO_BUZZER        = 19;   // buzzer ATIVO (oscilador interno)
const int PINO_LED_VERMELHO  = 18;
const int PINO_LED_AMARELO   = 2;
const int PINO_LED_VERDE     = 4;
const int PINO_BOTAO_REARME  = 15;   // botao NA para GND, pull-up interno

const bool BUZZER_ATIVO_EM_ALTO = true;

// --- TEMPOS -------------------------------------------------------------------
const uint32_t BAUD_RATE        = 115200;
const uint32_t TIMEOUT_LINK_MS  = 300;
const uint32_t DEBOUNCE_MS      = 50;
const uint32_t PULSO_MS         = 80;
const uint16_t MQTT_KEEPALIVE_S = 5;      // broker declara morto em ~1,5 x 5 s
const uint16_t MQTT_TIMEOUT_S   = 2;
const uint32_t RECONEXAO_MS     = 3000;
const uint32_t TELEMETRIA_MS    = 2000;

// --- ESTADO -------------------------------------------------------------------
enum Estado
{
  EST_FALHA,
  EST_BLOQUEADO,
  EST_LIBERADO
};

enum Causa
{
  CAUSA_LINK,      // watchdog de 300 ms venceu
  CAUSA_PC_S,      // PC mandou 'S' (visao: seguro)
  CAUSA_PC_D,      // PC mandou 'D' (visao: perigo ou interlock travado)
  CAUSA_REARME     // botao fisico
};

struct Evento
{
  uint8_t  de;
  uint8_t  para;
  uint8_t  causa;
  uint32_t tMs;
};

// Escritos SO no nucleo 1. O nucleo 0 le um instantaneo protegido por mux.
volatile Estado estado = EST_FALHA;
uint32_t nInterlocks     = 0;     // LIBERADO -> BLOQUEADO por 'D' do PC
uint32_t nFalhas         = 0;     // entradas em FALHA
uint32_t nRearmes        = 0;
uint32_t tLiberadoMs     = 0;
uint32_t tEntrouLiberado = 0;
volatile uint32_t eventosPerdidos = 0;

// Escritos no nucleo 1 (lerSerial), lidos tambem pela telemetria no nucleo 0.
volatile char     ultimoComando    = 'D';
volatile uint32_t tUltimoByte      = 0;
volatile bool     recebeuAlgumByte = false;

uint8_t  pulsosPendentes  = 0;
bool     buzzerLigado     = false;
uint32_t tBuzzer          = 0;

portMUX_TYPE  mux = portMUX_INITIALIZER_UNLOCKED;
QueueHandle_t filaEventos;

// Objetos de rede: usados SO dentro de tarefaMqtt (nucleo 0).
WiFiClient   wifiCliente;
PubSubClient mqtt(wifiCliente);
char topicoBase[64];


// --- TEXTOS -------------------------------------------------------------------

const char* nomeEstado(uint8_t e)
{
  switch (e)
  {
    case EST_FALHA:     return "FALHA";
    case EST_BLOQUEADO: return "BLOQUEADO";
    case EST_LIBERADO:  return "LIBERADO";
  }
  return "DESCONHECIDO";
}

const char* nomeCausa(uint8_t c)
{
  switch (c)
  {
    case CAUSA_LINK:   return "LINK";
    case CAUSA_PC_S:   return "PC_S";
    case CAUSA_PC_D:   return "PC_D";
    case CAUSA_REARME: return "REARME";
  }
  return "?";
}


// --- BUZZER -------------------------------------------------------------------

void escreverBuzzer(bool tocar)
{
  if (tocar == BUZZER_ATIVO_EM_ALTO)
  {
    digitalWrite(PINO_BUZZER, HIGH);
  }
  else
  {
    digitalWrite(PINO_BUZZER, LOW);
  }
}

void pulsar(uint8_t quantidade)
{
  pulsosPendentes = quantidade;
}

// Gera os pulsos sem delay(): alterna liga/desliga a cada PULSO_MS.
void atualizarBuzzer()
{
  if (millis() - tBuzzer < PULSO_MS)
  {
    return;
  }
  tBuzzer = millis();

  if (buzzerLigado)
  {
    buzzerLigado = false;
  }
  else if (pulsosPendentes > 0)
  {
    buzzerLigado = true;
    pulsosPendentes--;
  }
  escreverBuzzer(buzzerLigado);
}


// --- LEDS ---------------------------------------------------------------------

void escreverLed(int pino, bool aceso)
{
  if (aceso)
  {
    digitalWrite(pino, HIGH);
  }
  else
  {
    digitalWrite(pino, LOW);
  }
}

// Exatamente um LED aceso por vez.
void atualizarLeds()
{
  bool verde    = (estado == EST_LIBERADO);
  bool vermelho = (estado == EST_BLOQUEADO);
  bool amarelo  = !verde && !vermelho;

  escreverLed(PINO_LED_VERDE, verde);
  escreverLed(PINO_LED_VERMELHO, vermelho);
  escreverLed(PINO_LED_AMARELO, amarelo);
}


// --- ENTRADAS -----------------------------------------------------------------

void lerSerial()
{
  while (Serial.available() > 0)
  {
    int c = Serial.read();
    if (c != 'S' && c != 'D')
    {
      continue;   // '\r', '\n' e lixo de boot nao renovam o watchdog
    }

    // Pulsa so quando o comando muda; o heartbeat repetido fica mudo.
    if (c != ultimoComando)
    {
      if (c == 'S')
      {
        pulsar(1);
      }
      else
      {
        pulsar(2);
      }
    }

    ultimoComando    = (char)c;
    tUltimoByte      = millis();
    recebeuAlgumByte = true;
  }
}

bool linkEstaOk()
{
  if (!recebeuAlgumByte)
  {
    return false;
  }
  return (millis() - tUltimoByte) <= TIMEOUT_LINK_MS;
}

// true uma unica vez, na SOLTURA do botao. Botao travado nunca rearma.
bool rearmeSolicitado()
{
  static bool     leituraAnterior    = false;
  static bool     pressionadoEstavel = false;
  static uint32_t tMudanca           = 0;

  bool leitura = (digitalRead(PINO_BOTAO_REARME) == LOW);

  if (leitura != leituraAnterior)
  {
    leituraAnterior = leitura;
    tMudanca = millis();
    return false;
  }
  if (millis() - tMudanca < DEBOUNCE_MS)
  {
    return false;
  }
  if (leitura && !pressionadoEstavel)
  {
    pressionadoEstavel = true;
  }
  else if (!leitura && pressionadoEstavel)
  {
    pressionadoEstavel = false;
    return true;
  }
  return false;
}


// --- EVENTOS (nucleo 1 -> nucleo 0) -------------------------------------------

// Timeout ZERO: fila cheia descarta o evento e conta. O interlock nunca espera.
void mudarEstado(Estado novo, uint8_t causa)
{
  Estado anterior = estado;
  if (novo == anterior)
  {
    return;
  }

  uint32_t agora = millis();

  portENTER_CRITICAL(&mux);
  if (anterior == EST_LIBERADO)
  {
    tLiberadoMs += agora - tEntrouLiberado;
  }
  if (novo == EST_LIBERADO)
  {
    tEntrouLiberado = agora;
  }
  if (anterior == EST_LIBERADO && novo == EST_BLOQUEADO)
  {
    nInterlocks++;
  }
  if (novo == EST_FALHA)
  {
    nFalhas++;
  }
  if (causa == CAUSA_REARME)
  {
    nRearmes++;
  }
  estado = novo;
  portEXIT_CRITICAL(&mux);

  Evento ev;
  ev.de    = anterior;
  ev.para  = novo;
  ev.causa = causa;
  ev.tMs   = agora;
  if (xQueueSend(filaEventos, &ev, 0) != pdTRUE)
  {
    eventosPerdidos = eventosPerdidos + 1;
  }
}


// --- MAQUINA DE ESTADOS (mesma logica do Aula_08.ino) -------------------------

void transicionar(bool linkOk, bool rearme)
{
  switch (estado)
  {
    case EST_FALHA:
      if (linkOk && rearme)
      {
        mudarEstado(EST_BLOQUEADO, CAUSA_REARME);   // nunca direto para LIBERADO
      }
      break;

    case EST_BLOQUEADO:
      if (!linkOk)
      {
        mudarEstado(EST_FALHA, CAUSA_LINK);
      }
      else if (ultimoComando == 'S')
      {
        mudarEstado(EST_LIBERADO, CAUSA_PC_S);
      }
      break;

    case EST_LIBERADO:
      if (!linkOk)
      {
        mudarEstado(EST_FALHA, CAUSA_LINK);
      }
      else if (ultimoComando == 'D')
      {
        mudarEstado(EST_BLOQUEADO, CAUSA_PC_D);
      }
      break;
  }
}


// --- MQTT (SO NO NUCLEO 0) ----------------------------------------------------

void montarTopico(char* destino, size_t tamanho, const char* sufixo)
{
  snprintf(destino, tamanho, "%s/%s", topicoBase, sufixo);
}

void publicarEstado()
{
  char topico[96];
  montarTopico(topico, sizeof(topico), "estado");
  mqtt.publish(topico, nomeEstado(estado), true);
}

bool conectarMqtt()
{
  char topicoStatus[96];
  char clientId[48];

  montarTopico(topicoStatus, sizeof(topicoStatus), "status");
  snprintf(clientId, sizeof(clientId), "fiap-pc-%s", BANCADA);

  // Last Will: se o ESP32 sumir sem DISCONNECT, o broker publica "offline".
  bool ok = mqtt.connect(clientId, topicoStatus, 1, true, "offline");
  if (!ok)
  {
    Serial.printf("[MQTT] falha ao conectar, rc=%d\n", mqtt.state());
    return false;
  }

  mqtt.publish(topicoStatus, "online", true);
  publicarEstado();
  Serial.printf("[MQTT] conectado como %s\n", clientId);
  return true;
}

void publicarEventosPendentes()
{
  char topico[96];
  char json[160];
  Evento ev;

  montarTopico(topico, sizeof(topico), "evento");
  while (xQueueReceive(filaEventos, &ev, 0) == pdTRUE)
  {
    snprintf(json, sizeof(json),
             "{\"de\":\"%s\",\"para\":\"%s\",\"causa\":\"%s\",\"t_ms\":%lu}",
             nomeEstado(ev.de), nomeEstado(ev.para), nomeCausa(ev.causa),
             (unsigned long)ev.tMs);
    mqtt.publish(topico, json, false);
    publicarEstado();
  }
}

void publicarTelemetria()
{
  uint32_t agora = millis();
  uint8_t  e;
  uint32_t liberado;
  uint32_t interlocks;
  uint32_t falhas;
  uint32_t rearmes;
  char     cmd;
  uint32_t idadeLink;

  // Instantaneo coerente: campos lidos juntos, sem o nucleo 1 no meio.
  portENTER_CRITICAL(&mux);
  e          = estado;
  liberado   = tLiberadoMs;
  interlocks = nInterlocks;
  falhas     = nFalhas;
  rearmes    = nRearmes;
  cmd        = ultimoComando;
  uint32_t t = tUltimoByte;
  if (e == EST_LIBERADO)
  {
    liberado += agora - tEntrouLiberado;
  }
  portEXIT_CRITICAL(&mux);

  // O nucleo 1 pode ter carimbado um byte depois de 'agora' ser lido.
  idadeLink = 0;
  if (recebeuAlgumByte && agora > t)
  {
    idadeLink = agora - t;
  }

  float disponibilidade = 0.0f;
  if (agora > 0)
  {
    disponibilidade = (float)liberado / (float)agora;
  }

  char topico[96];
  char json[256];
  montarTopico(topico, sizeof(topico), "telemetria");
  snprintf(json, sizeof(json),
           "{\"estado\":\"%s\",\"ultimo_cmd\":\"%c\",\"idade_link_ms\":%lu,"
           "\"uptime_s\":%lu,\"liberado_s\":%lu,\"disp\":%.3f,"
           "\"interlocks\":%lu,\"falhas\":%lu,\"rearmes\":%lu,"
           "\"rssi\":%d,\"perdidos\":%lu}",
           nomeEstado(e), cmd, (unsigned long)idadeLink,
           (unsigned long)(agora / 1000), (unsigned long)(liberado / 1000),
           disponibilidade, (unsigned long)interlocks, (unsigned long)falhas,
           (unsigned long)rearmes, (int)WiFi.RSSI(), (unsigned long)eventosPerdidos);
  mqtt.publish(topico, json, false);
}

void tarefaMqtt(void* parametro)
{
  (void)parametro;

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);

  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
  mqtt.setSocketTimeout(MQTT_TIMEOUT_S);
  mqtt.setBufferSize(512);

  uint32_t tTentativa  = 0;
  uint32_t tTelemetria = 0;
  bool     primeira    = true;

  for (;;)
  {
    if (WiFi.status() != WL_CONNECTED)
    {
      vTaskDelay(pdMS_TO_TICKS(250));
      continue;
    }

    if (!mqtt.connected())
    {
      if (primeira || (millis() - tTentativa) > RECONEXAO_MS)
      {
        primeira   = false;
        tTentativa = millis();
        conectarMqtt();   // pode bloquear por segundos: aqui isso nao importa
      }
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }

    mqtt.loop();   // mantem o keepalive (PINGREQ)
    publicarEventosPendentes();

    if (millis() - tTelemetria > TELEMETRIA_MS)
    {
      tTelemetria = millis();
      publicarTelemetria();
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }
}


// --- ARDUINO ------------------------------------------------------------------

void setup()
{
  pinMode(PINO_BUZZER, OUTPUT);
  escreverBuzzer(false);

  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_LED_AMARELO, OUTPUT);
  pinMode(PINO_BOTAO_REARME, INPUT_PULLUP);

  Serial.begin(BAUD_RATE);
  atualizarLeds();

  snprintf(topicoBase, sizeof(topicoBase), "%s/%s", PREFIXO, BANCADA);
  filaEventos = xQueueCreate(16, sizeof(Evento));

  // Nucleo 0, prioridade 1. O loop() do Arduino roda no nucleo 1.
  xTaskCreatePinnedToCore(tarefaMqtt, "mqtt", 6144, NULL, 1, NULL, 0);
}

void loop()
{
  lerSerial();

  bool linkOk = linkEstaOk();
  bool rearme = rearmeSolicitado();
  if (rearme)
  {
    pulsar(1);
  }

  transicionar(linkOk, rearme);
  atualizarLeds();
  atualizarBuzzer();
}

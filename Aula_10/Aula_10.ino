/*
 * =============================================================================
 * Aula_10.ino  
 * Laboratorio 10 (Area de Seguranca) + envio dos dados para o broker MQTT.
 * Placa: ESP32 Dev Module | Arduino IDE | Biblioteca: PubSubClient (Nick O'Leary)
 *
 * O Python (Aula_10.py) NAO MUDA. Ele continua mandando pela serial:
 *   'S' = libera     'D' = trava     (a cada ~100 ms)
 *   300 ms sem receber nada -> FALHA. Sair de FALHA so com o botao de rearme.
 *
 * O ESP32 publica no broker (BASE = "fiap/pc/<BANCADA>"):
 *   BASE/status      "online" ou "offline" (o broker publica "offline" sozinho
 *                    se o ESP32 sumir: e o Last Will)
 *   BASE/estado      LIBERADO, BLOQUEADO ou FALHA   (a cada mudanca)
 *   BASE/telemetria  JSON a cada 2 segundos
 *
 *
 * LEDS: verde = LIBERADO   vermelho = BLOQUEADO   amarelo = FALHA
 * AVISO: demonstracao didatica, nao e dispositivo de seguranca.
 * =============================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>

// --- CONFIGURACAO (EDITE AQUI) ------------------------------------------------
const char* WIFI_SSID  = "FIAP-IOT";        // Nome da rede Wi-Fi, importante a sua rede wi-fi ter suporte a dispositivos de 2,4GHz devido ao ESP32 utilizar essa frequência 
const char* WIFI_SENHA = "F!@p25.IOT";      // Senha da rede Wi-Fi
const char* MQTT_HOST  = "35.172.192.195";  // IP do computador com o Mosquitto
const char* BANCADA    = "bancada0X";       // cada grupo usa um numero diferente

// --- PINOS --------------------------------------------------------------------
const int PINO_BUZZER       = 19;
const int PINO_LED_VERMELHO = 18;
const int PINO_LED_AMARELO  = 2;
const int PINO_LED_VERDE    = 4;
const int PINO_BOTAO_REARME = 15;   // botao para GND, pull-up interno

// --- TEMPOS -------------------------------------------------------------------
const unsigned long TIMEOUT_LINK_MS = 300;    // watchdog da serial
const unsigned long TELEMETRIA_MS   = 2000;   // envia telemetria a cada 2 s
const unsigned long RECONEXAO_MS    = 5000;   // tenta o broker a cada 5 s

// --- ESTADOS ------------------------------------------------------------------
const int FALHA     = 0;
const int BLOQUEADO = 1;
const int LIBERADO  = 2;

int  estado        = FALHA;
char ultimoComando = 'D';
bool recebeuByte   = false;
unsigned long tUltimoByte = 0;

// Contadores que vao para a telemetria
unsigned long interlocks = 0;   // vezes que a visao travou a maquina
unsigned long falhas     = 0;   // vezes que o watchdog derrubou

// Rede
WiFiClient   wifi;
PubSubClient mqtt(wifi);
char topicoStatus[64];
char topicoEstado[64];
char topicoTelemetria[64];
unsigned long tUltimaTentativa = 0;
unsigned long tUltimaTelemetria = 0;


// --- TEXTOS -------------------------------------------------------------------

const char* nomeEstado(int e)
{
  if (e == LIBERADO)
  {
    return "LIBERADO";
  }
  if (e == BLOQUEADO)
  {
    return "BLOQUEADO";
  }
  return "FALHA";
}


// --- SAIDAS -------------------------------------------------------------------

void atualizarLeds()
{
  digitalWrite(PINO_LED_VERDE,    estado == LIBERADO);
  digitalWrite(PINO_LED_VERMELHO, estado == BLOQUEADO);
  digitalWrite(PINO_LED_AMARELO,  estado == FALHA);
}

// Bip curto. Usa delay() de 80 ms: aceitavel, porque o watchdog e de 300 ms.
void bip()
{
  digitalWrite(PINO_BUZZER, HIGH);
  delay(80);
  digitalWrite(PINO_BUZZER, LOW);
}


// --- ENTRADAS -----------------------------------------------------------------

void lerSerial()
{
  while (Serial.available() > 0)
  {
    char c = Serial.read();
    if (c == 'S' || c == 'D')          // qualquer outro byte e ignorado
    {
      ultimoComando = c;
      tUltimoByte   = millis();
      recebeuByte   = true;
    }
  }
}

bool linkOk()
{
  if (!recebeuByte)
  {
    return false;
  }
  return (millis() - tUltimoByte) <= TIMEOUT_LINK_MS;
}

// Devolve true uma vez quando o botao e SOLTO (com debounce de 50 ms).
bool botaoRearme()
{
  static bool apertado = false;
  static unsigned long tMudanca = 0;

  bool leitura = (digitalRead(PINO_BOTAO_REARME) == LOW);
  if (millis() - tMudanca < 50)
  {
    return false;
  }
  if (leitura && !apertado)
  {
    apertado = true;
    tMudanca = millis();
  }
  else if (!leitura && apertado)
  {
    apertado = false;
    tMudanca = millis();
    return true;
  }
  return false;
}


// --- MQTT ---------------------------------------------------------------------

void publicarEstado()
{
  if (mqtt.connected())
  {
    mqtt.publish(topicoEstado, nomeEstado(estado), true);   // true = retido
  }
}

void publicarTelemetria()
{
  char json[160];
  snprintf(json, sizeof(json),
           "{\"estado\":\"%s\",\"ultimo_cmd\":\"%c\",\"interlocks\":%lu,"
           "\"falhas\":%lu,\"uptime_s\":%lu,\"rssi\":%d}",
           nomeEstado(estado), ultimoComando, interlocks, falhas,
           (unsigned long)(millis() / 1000), (int)WiFi.RSSI());
  mqtt.publish(topicoTelemetria, json);
}

void conectarBroker()
{
  char clientId[40];
  snprintf(clientId, sizeof(clientId), "fiap-pc-%s", BANCADA);

  // Last Will: se o ESP32 desaparecer, o broker publica "offline" no lugar dele.
  if (mqtt.connect(clientId, topicoStatus, 1, true, "offline"))
  {
    mqtt.publish(topicoStatus, "online", true);
    publicarEstado();
    Serial.println("[MQTT] conectado");
  }
  else
  {
    Serial.print("[MQTT] falhou, rc=");
    Serial.println(mqtt.state());
  }
}

// Chamada a cada volta do loop(). Nunca tenta conectar com a maquina LIBERADA.
void cuidarDaRede()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    return;                                  // o ESP32 reconecta o Wi-Fi sozinho
  }

  if (!mqtt.connected())
  {
    if (estado == LIBERADO)
    {
      return;                                // REGRA DE OURO: nao arrisca travar
    }
    if (millis() - tUltimaTentativa > RECONEXAO_MS)
    {
      tUltimaTentativa = millis();
      conectarBroker();                      // pode demorar alguns segundos
    }
    return;
  }

  mqtt.loop();                               // mantem a conexao viva

  if (millis() - tUltimaTelemetria > TELEMETRIA_MS)
  {
    tUltimaTelemetria = millis();
    publicarTelemetria();
  }
}


// --- MAQUINA DE ESTADOS -------------------------------------------------------

void mudarPara(int novo)
{
  if (novo == estado)
  {
    return;
  }
  if (estado == LIBERADO && novo == BLOQUEADO)
  {
    interlocks++;
  }
  if (novo == FALHA)
  {
    falhas++;
  }
  estado = novo;
  atualizarLeds();
  publicarEstado();
  bip();
}

void maquinaDeEstados()
{
  bool link   = linkOk();
  bool rearme = botaoRearme();

  if (estado == FALHA)
  {
    if (link && rearme)
    {
      mudarPara(BLOQUEADO);                  // nunca direto para LIBERADO
    }
  }
  else if (!link)
  {
    mudarPara(FALHA);                        // watchdog: 300 ms sem byte
  }
  else if (ultimoComando == 'S')
  {
    mudarPara(LIBERADO);
  }
  else
  {
    mudarPara(BLOQUEADO);
  }
}


// --- ARDUINO ------------------------------------------------------------------

void setup()
{
  pinMode(PINO_BUZZER, OUTPUT);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_LED_AMARELO, OUTPUT);
  pinMode(PINO_BOTAO_REARME, INPUT_PULLUP);
  atualizarLeds();

  Serial.begin(115200);

  snprintf(topicoStatus,     sizeof(topicoStatus),     "fiap/pc/%s/status", BANCADA);
  snprintf(topicoEstado,     sizeof(topicoEstado),     "fiap/pc/%s/estado", BANCADA);
  snprintf(topicoTelemetria, sizeof(topicoTelemetria), "fiap/pc/%s/telemetria", BANCADA);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);         // nao espera: conecta em segundo plano

  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setKeepAlive(5);                      // broker percebe queda em ~7,5 s
  mqtt.setSocketTimeout(1);                  // espera no maximo 1 s pela resposta
}

void loop()
{
  lerSerial();
  maquinaDeEstados();
  cuidarDaRede();
}


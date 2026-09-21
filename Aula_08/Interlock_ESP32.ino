/*
 * =============================================================================
 * Interlock_ESP32.ino
 * Lado microcontrolador dos Laboratorios 8 (Area de Seguranca) e 9 (EPI).
 * Placa: ESP32 Dev Module | Arduino IDE
 *
 * PROTOCOLO (PC -> ESP32), 115200 8N1, um byte ASCII:
 *   'S' = libera     'D' = trava     qualquer outro byte e ignorado
 * O Python reenvia o estado a cada ~100 ms (heartbeat).
 *
 * WATCHDOG: 300 ms sem byte valido -> FALHA.
 * REARME:   saindo de FALHA, so volta com link valido + botao de rearme.
 *
 * LEDS (sempre um so aceso):
 *   verde    = maquina em operacao (LIBERADO)
 *   vermelho = maquina travada (BLOQUEADO)
 *   amarelo  = qualquer outro estado (FALHA / aguardando rearme)
 *
 * BUZZER (pulsos):
 *   1 pulso  = botao de rearme / comando 'S' recebido
 *   2 pulsos = comando 'D' recebido
 *
 * AVISO: demonstracao didatica, nao e dispositivo de seguranca.
 * =============================================================================
 */

#include <Arduino.h>

// --- PINOS --------------------------------------------------------------------
const int PINO_BUZZER        = 19;   // buzzer ATIVO (oscilador interno)
const int PINO_LED_VERMELHO  = 18;
const int PINO_LED_AMARELO   = 2;
const int PINO_LED_VERDE     = 4;
const int PINO_BOTAO_REARME  = 15;   // botao NA para GND, pull-up interno


// Logica invertida: buzzer toca com nivel BAIXO.
const bool BUZZER_ATIVO_EM_ALTO = true;

// --- TEMPOS -------------------------------------------------------------------
const uint32_t BAUD_RATE        = 115200;
const uint32_t TIMEOUT_LINK_MS  = 300;
const uint32_t DEBOUNCE_MS      = 50;
const uint32_t PULSO_MS         = 80;    // duracao de cada bip e de cada pausa

// --- ESTADO -------------------------------------------------------------------
enum Estado
{
  EST_FALHA,       // sem link ou recem-ligado: exige rearme
  EST_BLOQUEADO,   // link ok, PC mandou 'D'
  EST_LIBERADO     // link ok, PC mandou 'S'
};

Estado   estado           = EST_FALHA;
char     ultimoComando    = 'D';
uint32_t tUltimoByte      = 0;
bool     recebeuAlgumByte = false;

uint8_t  pulsosPendentes  = 0;
bool     buzzerLigado     = false;
uint32_t tBuzzer          = 0;


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


// --- MAQUINA DE ESTADOS -------------------------------------------------------

void transicionar(bool linkOk, bool rearme)
{
  switch (estado)
  {
    case EST_FALHA:
      if (linkOk && rearme)
      {
        estado = EST_BLOQUEADO;   // nunca direto para LIBERADO
      }
      break;

    case EST_BLOQUEADO:
      if (!linkOk)
      {
        estado = EST_FALHA;
      }
      else if (ultimoComando == 'S')
      {
        estado = EST_LIBERADO;
      }
      break;

    case EST_LIBERADO:
      if (!linkOk)
      {
        estado = EST_FALHA;
      }
      else if (ultimoComando == 'D')
      {
        estado = EST_BLOQUEADO;
      }
      break;
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

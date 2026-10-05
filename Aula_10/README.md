# Aula 10 – Área de Segurança com MQTT

O mesmo Laboratório da aula 8, agora com o ESP32 publicando o estado da máquina num broker MQTT. 

> **Aviso:** o MQTT aqui é só supervisão. Se o broker ou o Wi-Fi caírem, a máquina não para e não libera: ela só some da tela. Quem protege continua sendo o watchdog de 300 ms do ESP32.

---

## O que você precisa ter

- [ ] O Laboratório 8 funcionando com o ESP32 (LED verde quando seguro)
- [ ] Wi-Fi **2,4 GHz** com senha simples (WPA2). Rede com portal de login no navegador não funciona
- [ ] Um computador na mesma rede rodando o Mosquitto (veja o passo 1)
- [ ] MQTT Explorer instalado (<https://mqtt-explorer.com>) para ver os dados chegando

---

## Passo 1 – Instalar a biblioteca

No Arduino IDE: **Ferramentas → Gerenciar Bibliotecas**, procure `PubSubClient` e instale a do autor **Nick O'Leary**.

---

## Passo 2 – Configurar e gravar o firmware

Abra o `Aula_08_MQTT.ino` e edite o bloco do começo:

```cpp
const char*    WIFI_SSID   = "LAB_IOT";
const char*    WIFI_SENHA  = "trocar_senha";
const char*    MQTT_HOST   = "192.168.0.10";
const char*    BANCADA     = "bancada01";
```

`BANCADA` tem que ser **diferente para cada grupo**. Dois ESP32 com o mesmo nome derrubam um ao outro do broker.

1. Feche o `Aula_10.py`, se estiver aberto.
2. Grave o firmware (placa **ESP32 Dev Module**).
3. Abra o Monitor Serial em 115200 e espere `[MQTT] conectado como fiap-pc-bancada01`.
4. **Feche o Monitor Serial.** Senão o Python não consegue abrir a porta.

---

## Passo 3 – Rodar o Aula_10.py normalmente

```
.venv\Scripts\python Aula_08.py
```

Com `PORTA_ESP32` apontando para a porta do ESP32, igual ao passo 11 do Laboratório 8. Aperte o botão de rearme: LED verde.

---

## Passo 4 – Ver os dados no broker

No MQTT Explorer, conecte no IP do broker, porta 1883, sem usuário. Abra `fiap → pc → bancada01`:

| Tópico | Retido | Quando chega | Conteúdo |
| --- | --- | --- | --- |
| `status` | sim | ao conectar e ao cair | `online`, ou `offline` publicado pelo broker (Last Will) |
| `estado` | sim | a cada mudança | `LIBERADO`, `BLOQUEADO` ou `FALHA` |
| `evento` | não | a cada mudança | `{"de":"LIBERADO","para":"BLOQUEADO","causa":"PC_D","t_ms":48211}` |
| `telemetria` | não | a cada 2 s | JSON abaixo |

```json
{"estado":"LIBERADO","ultimo_cmd":"S","idade_link_ms":42,"uptime_s":310,
 "liberado_s":188,"disp":0.606,"interlocks":7,"falhas":1,"rearmes":2,
 "rssi":-61,"perdidos":0}
```

| Campo | Significado |
| --- | --- |
| `ultimo_cmd` | último byte recebido do PC: `S` (seguro) ou `D` (perigo) |
| `idade_link_ms` | há quanto tempo chegou o último byte. Acima de 300 vira FALHA |
| `disp` | fração do tempo ligada em LIBERADO desde que o ESP32 ligou |
| `interlocks` | quantas vezes a visão travou a máquina (LIBERADO → BLOQUEADO) |
| `falhas` | quantas vezes o watchdog derrubou para FALHA |
| `rearmes` | quantas vezes o botão foi usado |
| `perdidos` | eventos descartados porque a fila encheu (deve ficar em 0) |

| `causa` no evento | O que aconteceu |
| --- | --- |
| `PC_S` | a visão mandou liberar |
| `PC_D` | a visão detectou perigo (ou o interlock do Python está travado) |
| `LINK` | 300 ms sem byte do PC: watchdog |
| `REARME` | botão de rearme apertado |

---

## Teste rápido

| O que você faz | O que tem que aparecer no broker |
| --- | --- |
| Mão entra no círculo | `evento` com `causa: PC_D`, `estado` = `BLOQUEADO`, `interlocks` sobe |
| Aperta Q no Python | `PC_D` e, 300 ms depois, `LINK`. `estado` = `FALHA` |
| Tira o USB do ESP32 | depois de uns 7,5 s, `status` = `offline` |

Algumas placas reiniciam quando a porta serial fecha. Se a sua fizer isso ao apertar Q, você verá `offline` e `online` piscarem no broker logo depois.

O último teste mostra a diferença entre os dois "watchdogs": o ESP32 percebe o PC calado em 300 ms, mas o broker só percebe o ESP32 morto em 1,5 × keepalive (5 s), porque uma placa sem energia não consegue avisar que saiu.

---

## O que o ESP32 não consegue publicar

Posição da mão, `d/R`, velocidade e a saída da MLP ficam no PC. O serial só carrega `S` ou `D`, então o ESP32 não tem esses números. Para publicá-los sem mexer no Python, o caminho seria outro processo no PC lendo os dados — não o ESP32.

---

## Deu erro?

| O que aparece | O que fazer |
| --- | --- |
| `PubSubClient.h: No such file or directory` | Instale a biblioteca (passo 2) |
| Monitor Serial mudo, sem `[MQTT]` | O ESP32 não entrou no Wi-Fi. Confira SSID, senha e se a rede é 2,4 GHz |
| `[MQTT] falha ao conectar, rc=-2` repetindo | Wi-Fi ok, broker inalcançável: IP errado, Mosquitto parado, firewall ou isolamento de clientes no roteador |
| `rc=2` | `BANCADA` com espaço ou acento |
| `status` alterna `online`/`offline` | Outro ESP32 com o mesmo `BANCADA` |
| `could not open port` no Python | Monitor Serial do Arduino IDE ainda aberto |
| Tudo funciona mas nada chega no MQTT Explorer | O MQTT Explorer está conectado em outro IP, ou o seu computador está em outra rede |


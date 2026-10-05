# Laboratório 10 – Área de Segurança com Supervisão MQTT

É o mesmo Laboratório 8: a webcam acompanha a sua mão e, se a mão entrar no círculo vermelho da tela ou vier rápido na direção dele, o programa manda o ESP32 parar a máquina.

A novidade da Aula 10 é que o ESP32 agora também publica o estado da máquina num broker MQTT. Com isso, um supervisório no navegador mostra as 12 bancadas da sala ao mesmo tempo, cada uma em verde (com conexão) ou vermelho (sem conexão).

> **Aviso:** isto é uma demonstração para aprender. Não serve para proteger uma máquina de verdade. Proteção real exige sensor certificado (cortina de luz tipo 4, norma ISO 13849-1).
>
> O MQTT aqui é **só supervisão**. Se o broker ou o Wi-Fi caírem, a máquina não para e não libera por causa disso: a bancada só some da tela. Quem trava a máquina continua sendo o watchdog de 300 ms do ESP32.

---

## Como usar este guia

- Cada bloco cinza é **um comando**. Copie, cole no terminal, aperte **Enter** e **espere terminar** antes de ir para o próximo.
- Não pule passos. Se um passo der erro, pare e vá direto para a seção [Deu erro?](#deu-erro).
- Os passos 1 a 5 você faz **uma vez só** por computador.
- **Já fez o Laboratório 8 neste computador?** Copie a pasta `.venv` e o `hand_landmarker.task` para a pasta da Aula 10, rode só o segundo comando do passo 4 (para instalar as bibliotecas novas) e continue do passo 6.

---

## O que você precisa ter

- [ ] Computador com Windows 10 ou 11
- [ ] Webcam funcionando
- [ ] Internet (para a instalação e para falar com o broker)
- [ ] Os arquivos `Aula_10.py`, `Aula_10.ino`, `supervisorio.py` e `requirements.txt` na mesma pasta
- [ ] Arduino IDE com o pacote de placas **esp32** (da Espressif) instalado, igual ao Laboratório 8
- [ ] O número da sua bancada (de `01` a `12`), passado pelo professor
- [ ] Wi-Fi **2,4 GHz** com senha simples (WPA2). Rede com página de login no navegador não funciona com o ESP32
- [ ] MQTT Explorer instalado (<https://mqtt-explorer.com>) para ver os dados chegando no broker

---

## Passo 1 – Instalar o Python 3.12

1. Entre em <https://www.python.org/downloads/windows/> e baixe o **Python 3.12**, versão **Windows installer (64-bit)**.
2. Abra o instalador.
3. **Marque a caixa "Add python.exe to PATH"** lá embaixo, antes de clicar em qualquer coisa.
4. Clique em **Install Now** e espere terminar.

Para conferir, abra o terminal (passo 2) e rode:

```
py -3.12 --version
```

Tem que aparecer `Python 3.12.` seguido de algum número. Se aparecer erro, o Python não foi instalado direito: repita o passo 1.

---

## Passo 2 – Abrir o terminal na pasta do projeto

1. Abra a pasta onde estão o `Aula_10.py` e o `requirements.txt`.
2. Clique na barra de endereço da pasta (onde aparece o caminho, lá em cima).
3. Apague o que estiver escrito, digite `powershell` e aperte **Enter**.

Vai abrir uma janela azul ou preta: esse é o terminal, já dentro da pasta certa.

Confira se você está no lugar certo:

```
dir
```

Na lista tem que aparecer `Aula_10.py`, `supervisorio.py` e `requirements.txt`. Se não aparecer, você abriu o terminal na pasta errada.

---

## Passo 3 – Criar o ambiente virtual

O ambiente virtual é uma pasta chamada `.venv` que guarda as bibliotecas só deste projeto, sem bagunçar o resto do computador.

```
py -3.12 -m venv .venv
```

Não aparece nada na tela. É normal. Espere o terminal liberar o cursor de novo.

---

## Passo 4 – Instalar as bibliotecas

Este comando demora de 2 a 5 minutos. Não feche o terminal.

```
.venv\Scripts\python -m pip install --upgrade pip
```

```
.venv\Scripts\python -m pip install -r requirements.txt
```

No final tem que aparecer `Successfully installed` e uma lista de nomes.

Confira se deu tudo certo:

```
.venv\Scripts\python -c "import cv2, mediapipe, sklearn, serial, paho.mqtt, flask; print('TUDO OK')"
```

Tem que aparecer `TUDO OK`. Qualquer outra coisa, vá para [Deu erro?](#deu-erro).

> **Por que `.venv\Scripts\python` em todo comando?** Assim você usa o Python do ambiente virtual sem precisar "ativar" nada. Isso evita o erro de permissão do PowerShell que costuma travar a aula.

---

## Passo 5 – Baixar o modelo da mão

O programa precisa de um arquivo chamado `hand_landmarker.task`. É ele que sabe encontrar a mão na imagem.

```
curl.exe -L -o hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

Confira se o arquivo chegou:

```
dir hand_landmarker.task
```

Tem que aparecer o arquivo com alguns megabytes (a coluna `Length` mostra o tamanho em bytes, na casa dos milhões). Se aparecer com 0 bytes ou não aparecer, rode o `curl.exe` de novo.

---

## Passo 6 – Configurar a porta (primeiro SEM o ESP32)

Na primeira vez você vai rodar sem a placa. Assim, se algo der errado, você sabe que o problema não é a porta serial.

Abra o script no Bloco de Notas:

```
notepad Aula_10.py
```

Procure esta linha, perto do começo do arquivo:

```python
PORTA_ESP32 = "COMX"
```

Troque por:

```python
PORTA_ESP32 = None
```

Atenção: `None` sem aspas e com **N maiúsculo**. Salve (**Ctrl + S**) e feche o Bloco de Notas.

> Se você deixar `"COMX"`, o programa fecha na hora com `[ERRO] Falha de comunicacao de borda`, porque não existe porta com esse nome.

---

## Passo 7 – Rodar o programa

```
.venv\Scripts\python Aula_10.py
```

A primeira vez pode levar uns 10 segundos para abrir. Vai aparecer uma janela com a imagem da câmera, um **círculo vermelho** embaixo e o título **MODO COLETA DE DADOS**.

No terminal aparece algo assim:

```
[VIDEO] resolucao pedida 1280x720, efetiva 1280x720
[VIDEO] raio da zona de risco = 201 px (28% da altura)
```

> **Clique uma vez em cima da janela do vídeo.** As teclas só funcionam quando a janela do vídeo está selecionada, não o terminal.

---

## Passo 8 – Coletar os exemplos

Aqui você ensina a IA. Ela só vai ser tão boa quanto os exemplos que você der.

**Exemplos SEGUROS (tecla S):**

1. Aperte **S**. Aparece `GRAVANDO SAFE` no canto de cima.
2. Mexa a mão **fora** do círculo, devagar. Afaste a mão do círculo também.
3. Aperte **S** de novo para parar.

**Exemplos de PERIGO (tecla D):**

1. Aperte **D**. Aparece `GRAVANDO DANGER`.
2. Coloque a mão **dentro** do círculo. Traga a mão **rápido** na direção dele, mesmo começando de longe.
3. Aperte **D** de novo para parar.

Regras para um bom dataset:

- Varie: perto, longe, devagar, rápido, de lados diferentes.
- Grave mais ou menos a mesma quantidade das duas classes.
- Se aparecer `MAO NAO DETECTADA`, a amostra não está sendo gravada. Melhore a luz ou aproxime a mão da câmera.

As duas barras no canto esquerdo mostram quantas amostras você já tem. Precisa de **30 de cada**.

---

## Passo 9 – Treinar a IA

Quando aparecer piscando **PRESSIONE T PARA TREINAR**, aperte **T**.

Olhe o terminal. Vai aparecer uma linha assim:

```
[IA] acuracia treino=0.983  holdout=0.944  regra geometrica=0.944
```

| Número | O que é |
| --- | --- |
| `treino` | Nota da IA nos exemplos que ela usou para aprender |
| `holdout` | Nota da IA nos exemplos que ela **nunca viu**. É a nota que importa |
| `regra geometrica` | Nota de uma regra simples, sem IA: "dentro do círculo ou chegando rápido é perigo" |

**Anote os três números.** Se `treino` for muito maior que `holdout`, a IA decorou em vez de aprender: aperte **E**, depois **C**, e colete de novo variando mais.

Se aparecer `A regra geometrica empatou ou superou a rede`, não é erro seu. Com só dois números de entrada, uma regra simples costuma ser tão boa quanto a rede. Esse é o resultado honesto do experimento.

---

## Passo 10 – Testar

Agora o programa está em **MODO INFERENCIA**.

| O que você faz | O que tem que aparecer |
| --- | --- |
| Nenhuma mão na tela | `STANDBY` (máquina liberada) |
| Mão longe do círculo, devagar | `OPERACAO SEGURA` em verde |
| Mão entrando no círculo | `!!! INTERLOCK ATIVADO !!!` com borda vermelha |
| Mão rápida vindo na direção do círculo | `!!! INTERLOCK ATIVADO !!!` antes de a mão chegar |

Depois que o interlock ativa, ele **não solta sozinho**, mesmo que você tire a mão. Aperte **R** para rearmar.

O painel de baixo mostra `MLP: x  regra geometrica: y`. Quando aparece `DIVERGEM`, a IA e a regra simples discordaram naquele momento.

Se quiser guardar os seus exemplos, volte para a coleta (**E**) e aperte **G**. Vai ser criado um arquivo `dataset_DATA_HORA.csv` na pasta.

Feche o programa com **Q** antes de ir para o próximo passo.

---

## Passo 11 – Configurar e gravar o firmware

**Instale a biblioteca MQTT.** No Arduino IDE: **Ferramentas → Gerenciar Bibliotecas**, procure `PubSubClient` e instale a do autor **Nick O'Leary**.

**Edite a configuração.** Abra o `Aula_10.ino` e altere o bloco do começo com os dados passados pelo professor:

```cpp
const char* WIFI_SSID  = "NOME_DA_REDE";
const char* WIFI_SENHA = "SENHA_DA_REDE";
const char* MQTT_HOST  = "IP_DO_BROKER";
const char* BANCADA    = "bancada0X";
```

O `BANCADA` é o campo que mais dá problema:

| Certo | Errado | Por quê |
| --- | --- | --- |
| `bancada03` | `bancada0X` | Esqueceu de trocar o X: o supervisório não mostra |
| `bancada03` | `bancada3` | Sem o zero o supervisório não reconhece |
| `bancada11` | `bancada011` | São sempre 2 dígitos, de `01` a `12` |
| um número por grupo | dois grupos com `bancada03` | Dois ESP32 com o mesmo nome derrubam um ao outro do broker |

**Grave e confira.**

1. Feche o `Aula_10.py`, se estiver aberto. Ele ocupa a porta serial.
2. Grave o firmware (placa **ESP32 Dev Module**).
3. Abra o Monitor Serial em **115200**. Em uns 5 a 10 segundos tem que aparecer `[MQTT] conectado`.
4. **Feche o Monitor Serial.** Senão o Python não consegue abrir a porta.

O ESP32 só tenta o broker a cada 5 segundos, e a primeira tentativa acontece 5 segundos depois de ligar. Se o Monitor Serial ficar mudo, o ESP32 ainda não entrou no Wi-Fi. Se aparecer `[MQTT] falhou, rc=` seguido de um número, veja a tabela [Deu erro?](#deu-erro).

---

## Passo 12 – Ligar o ESP32 ao Python

1. **Confira que o Monitor Serial do Arduino IDE está fechado.** Dois programas não usam a mesma porta ao mesmo tempo.
2. Conecte o ESP32 no USB.

Descubra em qual porta ele está:

```
.venv\Scripts\python -m serial.tools.list_ports
```

Vai aparecer algo como `COM5`. Se aparecerem várias, tire o cabo do ESP32, rode o comando de novo e veja qual sumiu: essa é a do ESP32.

Abra o script de novo:

```
notepad Aula_10.py
```

Troque `PORTA_ESP32 = None` pela sua porta, **com aspas**:

```python
PORTA_ESP32 = "COM5"
```

Salve, feche e rode:

```
.venv\Scripts\python Aula_10.py
```

No rodapé da janela tem que aparecer `serial: COM5` em verde.

**O ESP32 reinicia toda vez que o programa abre a porta.** Ele começa com o **LED amarelo** aceso, esperando o rearme, e se reconecta sozinho ao Wi-Fi e ao broker. Aperte e **solte** o **botão de rearme** da placa: o LED vai para o vermelho, porque no modo coleta o Python manda travar o tempo todo. O LED só fica verde depois do treino, no modo inferência.

| LED do ESP32 | Significado |
| --- | --- |
| Verde | Máquina em operação (`LIBERADO`) |
| Vermelho | Máquina travada (`BLOQUEADO`) |
| Amarelo | Falha ou aguardando rearme (`FALHA`, aperte o botão) |

O buzzer dá **1 pulso a cada mudança de estado** (qualquer troca de cor do LED).

Faça o teste mais importante da aula: com a máquina liberada (LED verde), aperte **Q** no Python. O LED tem que ir para o vermelho (o Python manda travar antes de sair) e, 300 ms depois, para o amarelo (o watchdog percebeu que o PC parou de falar). Rode o Python de novo: a máquina **não pode voltar sozinha**, precisa do botão de rearme.

> Tirar o cabo USB **não** testa o watchdog: sem o cabo a placa fica sem energia e os LEDs simplesmente apagam. Esse teste serve para outra coisa, veja o passo 13.

---

## Passo 13 – Ver os dados no broker

No MQTT Explorer, crie uma conexão com o IP do broker, porta **1883**, sem usuário e sem senha. Abra `fiap → pc → bancada0X` (o seu número):

| Tópico | Retido | Quando chega | Conteúdo |
| --- | --- | --- | --- |
| `status` | sim | ao conectar e ao cair | `online`, ou `offline` publicado pelo próprio broker (Last Will) |
| `estado` | sim | a cada mudança | `LIBERADO`, `BLOQUEADO` ou `FALHA` |
| `telemetria` | não | a cada 2 s | JSON abaixo |

"Retido" quer dizer que o broker guarda a última mensagem: quem conectar depois recebe na hora, sem esperar a próxima mudança.

```json
{"estado":"LIBERADO","ultimo_cmd":"S","interlocks":7,"falhas":1,"uptime_s":310,"rssi":-61}
```

| Campo | Significado |
| --- | --- |
| `estado` | estado atual da máquina |
| `ultimo_cmd` | último byte recebido do PC: `S` (seguro) ou `D` (perigo) |
| `interlocks` | quantas vezes a visão travou a máquina (`LIBERADO` → `BLOQUEADO`) |
| `falhas` | quantas vezes a máquina foi para `FALHA` (inclui a falha de quando o ESP32 liga) |
| `uptime_s` | segundos desde que o ESP32 ligou ou reiniciou |
| `rssi` | força do sinal Wi-Fi em dBm. Abaixo de -80 o sinal está fraco |

Os contadores zeram toda vez que o ESP32 reinicia, e ele reinicia toda vez que o Python abre a porta.

---

## Passo 14 – Supervisório das 12 bancadas

O `supervisorio.py` mostra todas as bancadas numa página web. Normalmente quem roda é o professor, mas você pode rodar no seu computador para ver a sua bancada.

Antes, confira no começo do arquivo se o `BROKER_HOST` é o mesmo IP que você colocou no `MQTT_HOST` do firmware:

```
notepad supervisorio.py
```

Rode em **outro terminal** (o primeiro continua com o `Aula_10.py`):

```
.venv\Scripts\python supervisorio.py
```

No terminal tem que aparecer `[MQTT] conectado em ... assinando 12 bancadas`. Abra no navegador: <http://localhost:5000>

A página já abre com as 12 bancadas em vermelho. Uma bancada fica **verde** só quando as três coisas são verdade ao mesmo tempo:

1. o supervisório está conectado ao broker;
2. o último `status` da bancada é `online`;
3. chegou `telemetria` dela nos últimos 6 segundos.

O supervisório só **observa**. Ele não manda comando nenhum para as bancadas. Para fechar, aperte **Ctrl + C** no terminal dele.

---

## Teste rápido do MQTT

| O que você faz | O que tem que aparecer |
| --- | --- |
| Mão entra no círculo | `estado` = `BLOQUEADO` no broker; na próxima telemetria `interlocks` sobe 1 |
| Aperta Q no Python | `estado` vai para `BLOQUEADO` e logo depois `FALHA`; `falhas` sobe 1 |
| Tira o USB do ESP32 | o supervisório fica vermelho em uns 6 s; o broker publica `status` = `offline` em uns 7,5 s |
| Recoloca o USB | `status` = `online` de novo; `uptime_s` volta para perto de 0 |

Algumas placas reiniciam quando a porta serial fecha. Se a sua fizer isso ao apertar Q, você verá `FALHA`, depois a bancada piscando no supervisório e `uptime_s` voltando a zero.

O teste do USB mostra a diferença entre os dois "watchdogs". O ESP32 percebe o PC calado em **300 ms**. O broker só percebe o ESP32 morto em **1,5 × keepalive = 1,5 × 5 s = 7,5 s**, porque uma placa sem energia não consegue avisar que saiu. O supervisório percebe antes do broker (6 s) porque conta as telemetrias que deixaram de chegar.

---

## Todas as teclas

| Tecla | O que faz | Funciona em |
| --- | --- | --- |
| S | Liga/desliga a gravação de exemplos SEGUROS | Coleta |
| D | Liga/desliga a gravação de exemplos de PERIGO | Coleta |
| T | Treina a IA (precisa de 30 de cada) | Coleta |
| C | Apaga todos os exemplos | Coleta |
| G | Salva os exemplos em arquivo CSV | Coleta |
| R | Rearma o interlock | Inferência |
| E | Volta para a coleta | Inferência |
| F | Liga/desliga tela cheia | Sempre |
| Q | Fecha o programa (e trava a máquina antes de sair) | Sempre |

---

## Como o programa decide (resumo)

O programa olha só para um ponto da mão: o **pulso** (bolinha azul-clara). A partir dele, calcula dois números 30 vezes por segundo:

- **d/R**: distância do pulso até o centro do círculo, dividida pelo raio. `d/R = 2` é longe, `d/R = 1` é na borda, `d/R = 0,5` já é dentro.
- **v**: velocidade de aproximação, em raios por segundo. Positiva = chegando, negativa = indo embora.

A IA (uma rede MLP pequena) recebe esses dois números e responde 0 (seguro) ou 1 (perigo). O programa guarda as últimas 7 respostas. Se **5 das 7** forem perigo, a máquina trava. Isso evita que um único quadro borrado pare a máquina à toa. O preço são uns 167 ms de atraso.

O Python manda para o ESP32 só uma letra: `S` (libera) ou `D` (trava), pelo menos a cada 100 ms. O ESP32 decide o resto e publica no broker.

---

## Por que o ESP32 não conecta no broker com a máquina liberada

Conectar no broker pode travar o ESP32 por alguns segundos. Durante esse tempo ele não lê a serial e o watchdog de 300 ms não roda. Se a máquina estivesse liberada, ela ficaria liberada sem ninguém vigiando.

Por isso o firmware só tenta conectar quando a máquina está `BLOQUEADO` ou `FALHA`. A consequência aparece no supervisório: se a sua bancada perder o broker com o LED verde, ela fica vermelha na tela **até a próxima vez que a máquina travar**. Não é defeito. Ponha a mão no círculo, rearme com **R**, e em até 5 s ela volta.

---

## O que o ESP32 não consegue publicar

Posição da mão, `d/R`, velocidade e a saída da MLP ficam no PC. O serial só carrega `S` ou `D`, então o ESP32 não tem esses números. Para publicá-los, o caminho seria o próprio PC (outro processo ou o Python publicando no broker), não o ESP32.

---

## Limitações desta versão

Para discutir em sala, não para corrigir agora:

- O watchdog e o MQTT rodam no mesmo `loop()`. A regra acima evita a reconexão com a máquina liberada, mas o envio da telemetria também acontece com a máquina liberada. Com o Wi-Fi muito ruim, um envio pode demorar mais que 300 ms, e nesse intervalo o watchdog não roda.
- O broker é aberto: sem usuário, sem senha e sem criptografia. Qualquer pessoa na rede pode ler os tópicos e também publicar neles, inclusive um `online` falso que deixa uma bancada verde no supervisório.
- `interlocks` e `falhas` zeram a cada reinício do ESP32. Para ter histórico, alguém precisa gravar as mensagens (um banco de dados assinando os tópicos, por exemplo).

---

## Deu erro?

| O que aparece | O que fazer |
| --- | --- |
| `'py' não é reconhecido como nome de cmdlet` | O Python não foi instalado ou faltou marcar "Add python.exe to PATH". Refaça o passo 1 |
| `O sistema não pode encontrar o caminho especificado` ao usar `.venv\Scripts\python` | O passo 3 não foi feito nesta pasta. Rode `dir` e confira se existe a pasta `.venv` |
| `No module named 'cv2'` ou `No module named 'mediapipe'` | O passo 4 não terminou. Rode de novo o `pip install -r requirements.txt` |
| `No module named 'paho'` ou `No module named 'flask'` | Você copiou a `.venv` do Laboratório 8. Rode de novo o `pip install -r requirements.txt` |
| `ERRO CRITICO Falha ao carregar 'hand_landmarker.task'` | O arquivo do modelo não está na pasta. Refaça o passo 5 |
| `ERRO CRITICO Nenhuma camera disponivel no indice 0` | Feche Teams, Zoom, Meet ou qualquer programa usando a câmera. Se não resolver, troque `CAMERA_INDEX = 0` por `CAMERA_INDEX = 1` no script |
| `[ERRO] Falha de comunicacao de borda` | Porta errada, `"COMX"` ainda no script, ou Monitor Serial aberto. Veja os passos 6 e 12 |
| `could not open port 'COM5': PermissionError` | Outro programa está usando a porta. Feche o Monitor Serial do Arduino IDE |
| As teclas não fazem nada | Clique em cima da janela do vídeo antes de apertar as teclas |
| `MAO NAO DETECTADA` o tempo todo | Acenda a luz, saia da frente da janela (contraluz), aproxime a mão |
| O interlock dispara sozinho sem parar | Os exemplos ficaram ruins. Aperte **E**, depois **C**, e colete de novo com mais cuidado |
| LED amarelo aceso e nada acontece | O ESP32 está esperando o rearme. Aperte e solte o botão da placa |
| O ESP32 cai para o amarelo sozinho durante o uso | O computador está lento (perto de 3 fps ou menos, veja no rodapé). Feche outros programas |
| `PubSubClient.h: No such file or directory` | Instale a biblioteca (passo 11) |
| Monitor Serial mudo, sem nenhuma linha `[MQTT]` | O ESP32 não entrou no Wi-Fi. Confira SSID, senha e se a rede é 2,4 GHz |
| `[MQTT] falhou, rc=-2` repetindo | Wi-Fi ok, broker inalcançável: IP errado, broker desligado, porta 1883 bloqueada pela rede ou isolamento de clientes no roteador |
| `[MQTT] falhou, rc=-4` | O broker demorou mais de 1 s para responder. Sinal fraco ou rede congestionada |
| `[MQTT] falhou, rc=2` | O broker recusou o nome do ESP32. Confira o `BANCADA` (passo 11) |
| `[MQTT] falhou, rc=5` | O broker exige usuário e senha. Avise o professor |
| `status` alterna `online`/`offline` sem parar | Outro ESP32 está com o mesmo `BANCADA` |
| Bancada vermelha no supervisório com o LED verde | Ela perdeu o broker com a máquina liberada. Veja [Por que o ESP32 não conecta no broker com a máquina liberada](#por-que-o-esp32-não-conecta-no-broker-com-a-máquina-liberada) |
| Bancada nunca aparece no supervisório | `BANCADA` fora do padrão `bancada01` a `bancada12`, ou `BROKER_HOST` do supervisório diferente do `MQTT_HOST` do firmware |
| Supervisório mostra `broker ... DESCONECTADO` | IP do broker errado no `supervisorio.py`, ou o computador está sem internet |
| Tudo funciona mas nada chega no MQTT Explorer | O MQTT Explorer está conectado em outro IP, ou você abriu o tópico de outra bancada |

---

## Da próxima vez (resumo)

Depois que tudo foi instalado, para usar de novo basta abrir o terminal na pasta (passo 2) e rodar:

```
.venv\Scripts\python Aula_10.py
```

E, se quiser o supervisório, em outro terminal:

```
.venv\Scripts\python supervisorio.py
```

O modelo treinado não é salvo: toda vez que o programa abre, ele volta para a coleta.

---

## Linux e macOS

Os passos são os mesmos, mudando só os comandos:

| Windows | Linux / macOS |
| --- | --- |
| `py -3.12 -m venv .venv` | `python3 -m venv .venv` |
| `.venv\Scripts\python` | `.venv/bin/python` |
| `curl.exe -L -o ...` | `curl -L -o ...` |
| `notepad Aula_10.py` | `nano Aula_10.py` |
| Porta `"COM5"` | Porta `"/dev/ttyUSB0"` (Linux) ou `"/dev/cu.usbserial-XXXX"` (macOS) |

No Linux, se der erro de permissão na porta serial, rode uma vez `sudo usermod -a -G dialout $USER` e reinicie o computador.

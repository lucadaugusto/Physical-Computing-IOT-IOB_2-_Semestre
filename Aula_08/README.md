# Laboratório 8 – Área de Segurança (Cerca Virtual)

A webcam acompanha a sua mão. Se a mão entrar no círculo vermelho da tela, ou vier rápido na direção dele, o programa manda o ESP32 parar a máquina.

Você mesmo ensina a IA: grava exemplos de mão em situação segura e em situação de perigo, aperta uma tecla, e o programa aprende com esses exemplos.

> **Aviso:** isto é uma demonstração para aprender. Não serve para proteger uma máquina de verdade. Proteção real exige sensor certificado (cortina de luz tipo 4, norma ISO 13849-1).

---

## Como usar este guia

- Cada bloco cinza é **um comando**. Copie, cole no terminal, aperte **Enter** e **espere terminar** antes de ir para o próximo.
- Não pule passos. Se um passo der erro, pare e vá direto para a seção [Deu erro?](#deu-erro).
- Os passos 1 a 5 você faz **uma vez só** por computador.

---

## O que você precisa ter

- [ ] Computador com Windows 10 ou 11
- [ ] Webcam funcionando
- [ ] Internet (só para a instalação)
- [ ] Os arquivos `Aula_08.py` e `requirements.txt` na mesma pasta
- [ ] ESP32 com o firmware `Aula_08.ino` gravado (só no passo 11)

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

1. Abra a pasta onde estão o `Aula_08.py` e o `requirements.txt`.
2. Clique na barra de endereço da pasta (onde aparece o caminho, lá em cima).
3. Apague o que estiver escrito, digite `powershell` e aperte **Enter**.

Vai abrir uma janela azul ou preta: esse é o terminal, já dentro da pasta certa.

Confira se você está no lugar certo:

```
dir
```

Na lista tem que aparecer `Aula_08.py` e `requirements.txt`. Se não aparecer, você abriu o terminal na pasta errada.

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
.venv\Scripts\python -c "import cv2, mediapipe, sklearn, serial; print('TUDO OK')"
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
notepad Aula_08.py
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
.venv\Scripts\python Aula_08.py
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

---

## Passo 11 – Ligar o ESP32

Só faça este passo depois que o passo 10 estiver funcionando.

1. Feche o programa com **Q**.
2. **Feche o Monitor Serial do Arduino IDE**, se estiver aberto. Dois programas não usam a mesma porta ao mesmo tempo.
3. Conecte o ESP32 no USB.

Descubra em qual porta ele está:

```
.venv\Scripts\python -m serial.tools.list_ports
```

Vai aparecer algo como `COM5`. Se aparecerem várias, tire o cabo do ESP32, rode o comando de novo e veja qual sumiu: essa é a do ESP32.

Abra o script de novo:

```
notepad Aula_08.py
```

Troque `PORTA_ESP32 = None` pela sua porta, **com aspas**:

```python
PORTA_ESP32 = "COM5"
```

Salve, feche e rode:

```
.venv\Scripts\python Aula_08.py
```

No rodapé da janela tem que aparecer `serial: COM5` em verde.

**O ESP32 reinicia toda vez que o programa abre a porta.** Ele começa com o **LED amarelo** aceso, esperando o rearme. Isso é normal: aperte e solte o **botão de rearme** da placa. O buzzer dá um pulso.

| LED do ESP32 | Significado |
| --- | --- |
| Verde | Máquina em operação |
| Vermelho | Máquina travada |
| Amarelo | Falha ou aguardando rearme (aperte o botão) |

| Buzzer | Significado |
| --- | --- |
| 1 pulso | Botão de rearme apertado, ou o PC mandou liberar |
| 2 pulsos | O PC mandou travar |

Faça o teste mais importante da aula: com a máquina liberada (LED verde), **tire o cabo USB**. Em menos de meio segundo o LED tem que sair do verde. Recoloque o cabo: a máquina **não pode voltar sozinha**, precisa do botão de rearme.

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

---

## Deu erro?

| O que aparece | O que fazer |
| --- | --- |
| `'py' não é reconhecido como nome de cmdlet` | O Python não foi instalado ou faltou marcar "Add python.exe to PATH". Refaça o passo 1 |
| `O sistema não pode encontrar o caminho especificado` ao usar `.venv\Scripts\python` | O passo 3 não foi feito nesta pasta. Rode `dir` e confira se existe a pasta `.venv` |
| `No module named 'cv2'` ou `No module named 'mediapipe'` | O passo 4 não terminou. Rode de novo o `pip install -r requirements.txt` |
| `ERRO CRITICO Falha ao carregar 'hand_landmarker.task'` | O arquivo do modelo não está na pasta. Refaça o passo 5 |
| `ERRO CRITICO Nenhuma camera disponivel no indice 0` | Feche Teams, Zoom, Meet ou qualquer programa usando a câmera. Se não resolver, troque `CAMERA_INDEX = 0` por `CAMERA_INDEX = 1` no script |
| `[ERRO] Falha de comunicacao de borda` | Porta errada, `"COMX"` ainda no script, ou Monitor Serial aberto. Veja os passos 6 e 11 |
| `could not open port 'COM5': PermissionError` | Outro programa está usando a porta. Feche o Monitor Serial do Arduino IDE |
| As teclas não fazem nada | Clique em cima da janela do vídeo antes de apertar as teclas |
| `MAO NAO DETECTADA` o tempo todo | Acenda a luz, saia da frente da janela (contraluz), aproxime a mão |
| O interlock dispara sozinho sem parar | Os exemplos ficaram ruins. Aperte **E**, depois **C**, e colete de novo com mais cuidado |
| LED amarelo aceso e nada acontece | O ESP32 está esperando o rearme. Aperte e solte o botão da placa |
| O ESP32 cai para o amarelo sozinho durante o uso | O computador está lento (menos de 5 fps, veja no rodapé). Feche outros programas |

---

## Da próxima vez (resumo)

Depois que tudo foi instalado, para usar de novo basta abrir o terminal na pasta (passo 2) e rodar:

```
.venv\Scripts\python Aula_08.py
```

---

## Linux e macOS

Os passos são os mesmos, mudando só os comandos:

| Windows | Linux / macOS |
| --- | --- |
| `py -3.12 -m venv .venv` | `python3 -m venv .venv` |
| `.venv\Scripts\python` | `.venv/bin/python` |
| `curl.exe -L -o ...` | `curl -L -o ...` |
| `notepad Aula_08.py` | `nano Aula_08.py` |
| Porta `"COM5"` | Porta `"/dev/ttyUSB0"` (Linux) ou `"/dev/cu.usbserial-XXXX"` (macOS) |

No Linux, se der erro de permissão na porta serial, rode uma vez `sudo usermod -a -G dialout $USER` e reinicie o computador.


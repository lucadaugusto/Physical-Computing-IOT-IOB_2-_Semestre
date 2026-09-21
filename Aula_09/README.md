# Laboratório 9 – EPI Segurança (Óculos de Proteção)

A webcam olha o seu rosto. Com óculos de proteção, a máquina funciona. Sem os óculos, o programa manda o ESP32 parar a máquina.

Você mesmo ensina a IA: grava exemplos com óculos e sem óculos, aperta uma tecla, e o programa aprende com esses exemplos.

> **Aviso:** isto é uma demonstração para aprender. Não serve para controlar uma máquina de verdade. Um intertravamento real por EPI exige avaliação de risco e equipamento certificado (norma ISO 13849-1).

---

## Como usar este guia

- Cada bloco cinza é **um comando**. Copie, cole no terminal, aperte **Enter** e **espere terminar** antes de ir para o próximo.
- Não pule passos. Se um passo der erro, pare e vá direto para a seção [Deu erro?](#deu-erro).
- Os passos 1 a 5 você faz **uma vez só** por computador.

> **Já fez o Laboratório 8 neste computador?** O Python já está instalado: pule o passo 1. Os passos 3 a 5 precisam ser feitos de novo, porque esta é outra pasta.

---

## O que você precisa ter

- [ ] Computador com Windows 10 ou 11
- [ ] Webcam funcionando
- [ ] Internet (só para a instalação)
- [ ] Os arquivos `Aula_09.py` e `requirements.txt` na mesma pasta
- [ ] Um par de **óculos de proteção**
- [ ] Um colega para gravar junto (recomendado)
- [ ] ESP32 com o firmware `Interlock_ESP32.ino` gravado (só no passo 12)

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

1. Abra a pasta onde estão o `Aula_09.py` e o `requirements.txt`.
2. Clique na barra de endereço da pasta (onde aparece o caminho, lá em cima).
3. Apague o que estiver escrito, digite `powershell` e aperte **Enter**.

Vai abrir uma janela azul ou preta: esse é o terminal, já dentro da pasta certa.

Confira se você está no lugar certo:

```
dir
```

Na lista tem que aparecer `Aula_09.py` e `requirements.txt`. Se não aparecer, você abriu o terminal na pasta errada.

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

## Passo 5 – Baixar o modelo do rosto

O programa precisa de um arquivo chamado `face_landmarker.task`. É ele que sabe encontrar o rosto e os olhos na imagem.

```
curl.exe -L -o face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

Confira se o arquivo chegou:

```
dir face_landmarker.task
```

Tem que aparecer o arquivo com alguns megabytes (a coluna `Length` mostra o tamanho em bytes, na casa dos milhões). Se aparecer com 0 bytes ou não aparecer, rode o `curl.exe` de novo.

> **Atenção:** este laboratório usa `face_landmarker.task`, não o `hand_landmarker.task` do Laboratório 8. Um não substitui o outro.

---

## Passo 6 – Configurar a porta (primeiro SEM o ESP32)

Na primeira vez você vai rodar sem a placa. Assim, se algo der errado, você sabe que o problema não é a porta serial.

Abra o script no Bloco de Notas:

```
notepad Aula_09.py
```

Procure esta linha, perto do começo do arquivo:

```python
PORTA_ESP32 = "COMX"
```

Troque por:

```python
PORTA_ESP32 = None
```

Atenção: `None` sem aspas e com **N maiúsculo**. Pode deixar o comentário que vem depois do `#`. Salve (**Ctrl + S**) e feche o Bloco de Notas.

> Se você deixar `"COMX"`, o programa fecha na hora com `[ERRO] Falha de comunicacao de borda`, porque não existe porta com esse nome.

---

## Passo 7 – Rodar o programa

```
.venv\Scripts\python Aula_09.py
```

A primeira vez pode levar uns 10 segundos para abrir. Vai aparecer uma janela com a imagem da câmera e o título **MODO COLETA - EPI OCULAR**.

Olhe para a câmera. Tem que aparecer:

- dois pontinhos azuis nos seus olhos, ligados por uma linha;
- no canto direito, duas imagens pequenas: em cima a região dos seus olhos, **endireitada**; embaixo as linhas (bordas) que o programa encontrou nela.

Se as imagens pequenas não aparecem, o rosto não está sendo detectado: chegue mais perto (menos de 1,5 m) ou melhore a luz.

> **Clique uma vez em cima da janela do vídeo.** As teclas só funcionam quando a janela do vídeo está selecionada, não o terminal.

---

## Passo 8 – Coletar os exemplos

Aqui você ensina a IA. Ela só vai ser tão boa quanto os exemplos que você der.

**Exemplos COM óculos (tecla S):**

1. Coloque os óculos de proteção.
2. Aperte **S**. Aparece `GRAVANDO COM OCULOS` à esquerda.
3. Mexa a cabeça devagar: vire um pouco para os lados, incline, chegue perto (uns 50 cm) e vá mais longe (uns 1,5 m).
4. Aperte **S** de novo para parar.

**Exemplos SEM óculos (tecla D):**

1. Tire os óculos.
2. Aperte **D**. Aparece `GRAVANDO SEM OCULOS`.
3. Faça os mesmos movimentos: perto, longe, virando e inclinando.
4. Aperte **D** de novo para parar.

Regras para um bom dataset:

- Varie posição, distância e luz **nas duas classes**. Se você só gravar "com óculos" perto e "sem óculos" longe, a IA aprende a distância, não os óculos.
- Grave mais ou menos a mesma quantidade das duas classes.
- Se aparecer `ROSTO NAO DETECTADO`, a amostra não está sendo gravada.
- **Grave com mais de uma pessoa.** Com um rosto só, a IA aprende o seu rosto, não os óculos (veja o passo 9).

As duas barras no canto esquerdo mostram quantas amostras você já tem. Precisa de **40 de cada**.

---

## Passo 9 – Juntar os exemplos de vários colegas (recomendado)

O programa consegue somar os exemplos de várias pessoas.

1. Cada colega grava os seus exemplos (passo 8) e aperta **G**. Vai ser criado um arquivo `epi_dataset_DATA_HORA.csv` na pasta.
2. Copie todos esses arquivos `.csv` para a pasta de um computador só.
3. Nesse computador, rode o programa e, no modo coleta, aperte **L** **uma única vez**.

O terminal mostra quantas amostras foram carregadas e de quais arquivos:

```
[DADOS] 240 amostras carregadas de 3 arquivo(s): epi_dataset_...
```

> Apertar **L** duas vezes carrega os mesmos arquivos de novo e duplica os exemplos. Se isso acontecer, aperte **C** para limpar e depois **L** uma vez só.

---

## Passo 10 – Treinar a IA

Quando aparecer piscando **PRESSIONE T PARA TREINAR**, aperte **T**.

Olhe o terminal. Vai aparecer uma linha assim:

```
[IA] treino=0.990  holdout=0.910  limiar simples=0.850
```

| Número | O que é |
| --- | --- |
| `treino` | Nota da IA nos exemplos que ela usou para aprender |
| `holdout` | Nota da IA nos exemplos que ela **nunca viu**. É a nota que importa |
| `limiar simples` | Nota de uma regra sem IA: "pouca linha em volta dos olhos = sem óculos" |

**Anote os três números.**

Se aparecer esta mensagem:

```
[IA] Gap treino-holdout alto: overfitting.
```

a IA decorou em vez de aprender. Aperte **E**, depois **C**, e colete de novo com mais variação e mais pessoas.

Se o `holdout` da IA não for maior que o `limiar simples`, a rede não está ganhando nada em relação a uma regra de uma linha. Anote isso: é um resultado do experimento, não um erro seu.

---

## Passo 11 – Testar

Agora o programa está em **MODO INFERENCIA**.

| O que você faz | O que tem que aparecer |
| --- | --- |
| Rosto na tela, com óculos | `EPI DETECTADO - OPERACAO LIBERADA` em verde |
| Tira os óculos | `FALTA EPI - MAQUINA BLOQUEADA` com borda vermelha |
| Sai da frente da câmera | `AGUARDANDO OPERADOR` (máquina **parada**) |

Depois que o bloqueio ativa, ele **não solta sozinho**, mesmo que você coloque os óculos de volta. Aperte **R** para rearmar.

**Diferença importante em relação ao Laboratório 8:** lá, ninguém na tela liberava a máquina. Aqui, ninguém na tela **bloqueia** a máquina. Se o programa não enxerga o operador, ele não tem como saber se o operador está de óculos, então fica no lado seguro.

**O desafio da aula:** coloque **óculos de grau** (ou de sol) e veja o que o sistema responde. Depois grave óculos de grau como **SEM óculos (D)**, treine de novo e compare o `holdout`. Tente explicar o resultado com a seção [Como o programa decide](#como-o-programa-decide-resumo).

---

## Passo 12 – Ligar o ESP32

Só faça este passo depois que o passo 11 estiver funcionando.

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
notepad Aula_09.py
```

Troque `PORTA_ESP32 = None` pela sua porta, **com aspas**:

```python
PORTA_ESP32 = "COM5"
```

Salve, feche e rode:

```
.venv\Scripts\python Aula_09.py
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
| S | Liga/desliga a gravação COM óculos | Coleta |
| D | Liga/desliga a gravação SEM óculos | Coleta |
| T | Treina a IA (precisa de 40 de cada) | Coleta |
| C | Apaga todos os exemplos | Coleta |
| G | Salva os exemplos em arquivo CSV | Coleta |
| L | Carrega todos os `epi_dataset_*.csv` da pasta | Coleta |
| R | Rearma o bloqueio | Inferência |
| E | Volta para a coleta | Inferência |
| F | Liga/desliga tela cheia | Sempre |
| Q | Fecha o programa (e trava a máquina antes de sair) | Sempre |

---

## Como o programa decide (resumo)

A ideia é simples: **óculos têm aro, e aro é linha**. Sem óculos, há bem menos linha em volta dos olhos.

1. O MediaPipe encontra o rosto e o programa pega os cantos dos dois olhos.
2. Com esses pontos, o programa **recorta e endireita** a região dos olhos num retângulo de 160×64 pixels. Funciona como uma foto 3x4: não importa se você está longe, perto ou com a cabeça torta, os olhos sempre caem no mesmo lugar do recorte.
3. Se os olhos estiverem a menos de 25 pixels um do outro, o rosto está longe demais e o quadro é ignorado.
4. O programa realça o contraste e marca as linhas (bordas) do recorte. São as linhas que aparecem na miniatura de baixo.
5. Dessas linhas saem **15 números**: quanta linha há em cada olho, na ponte do nariz, em cima e embaixo; a força e a direção das linhas; e a nitidez da imagem.
6. A IA (uma rede MLP) recebe os 15 números e responde 0 (com óculos) ou 1 (sem óculos).
7. O programa guarda as últimas 9 respostas. Se **6 das 9** forem "sem óculos", a máquina bloqueia. Isso evita que uma piscada ou um reflexo parem a máquina à toa.

**O limite do método:** os 15 números medem linhas, não o tipo de lente. Óculos de grau também têm aro. Por isso o sistema pode aceitar óculos de grau como se fossem EPI. Um sistema que resolvesse isso precisaria de um detector treinado com fotos rotuladas dos dois tipos de óculos.

---

## Deu erro?

| O que aparece | O que fazer |
| --- | --- |
| `'py' não é reconhecido como nome de cmdlet` | O Python não foi instalado ou faltou marcar "Add python.exe to PATH". Refaça o passo 1 |
| `O sistema não pode encontrar o caminho especificado` ao usar `.venv\Scripts\python` | O passo 3 não foi feito nesta pasta. Rode `dir` e confira se existe a pasta `.venv` |
| `No module named 'cv2'` ou `No module named 'mediapipe'` | O passo 4 não terminou. Rode de novo o `pip install -r requirements.txt` |
| `ERRO CRITICO Falha ao carregar 'face_landmarker.task'` | O arquivo do modelo não está na pasta, ou você baixou o da mão. Refaça o passo 5 |
| `can't open file ... EPI_Seguran?a.py` | O terminal não entendeu o "ç" do nome. Renomeie o arquivo para `EPI_Seguranca.py` e use esse nome nos comandos |
| `ERRO CRITICO Nenhuma camera no indice 0` | Feche Teams, Zoom, Meet ou qualquer programa usando a câmera. Se não resolver, troque `CAMERA_INDEX = 0` por `CAMERA_INDEX = 1` no script |
| `[ERRO] Falha de comunicacao de borda` | Porta errada, `"COMX"` ainda no script, ou Monitor Serial aberto. Veja os passos 6 e 12 |
| `could not open port 'COM5': PermissionError` | Outro programa está usando a porta. Feche o Monitor Serial do Arduino IDE |
| As teclas não fazem nada | Clique em cima da janela do vídeo antes de apertar as teclas |
| As miniaturas não aparecem / `ROSTO NAO DETECTADO` | Chegue mais perto, acenda a luz, saia da frente da janela (contraluz), tire boné ou capuz |
| `Gap treino-holdout alto: overfitting` | Colete de novo com mais variação de posição, luz e **pessoas diferentes** |
| Fica sempre em `FALTA EPI`, mesmo com óculos | Os exemplos ficaram ruins ou muito parecidos entre as classes. Aperte **E**, depois **C**, e colete de novo |
| O número de amostras dobrou do nada | Você apertou **L** duas vezes. Aperte **C** e depois **L** uma vez só |
| LED amarelo aceso e nada acontece | O ESP32 está esperando o rearme. Aperte e solte o botão da placa |
| O ESP32 cai para o amarelo sozinho durante o uso | O computador está lento (menos de 5 fps, veja no rodapé). Feche outros programas |

---

## Da próxima vez (resumo)

Depois que tudo foi instalado, para usar de novo basta abrir o terminal na pasta (passo 2) e rodar:

```
.venv\Scripts\python Aula_09.py
```

---

## Linux e macOS

Os passos são os mesmos, mudando só os comandos:

| Windows | Linux / macOS |
| --- | --- |
| `py -3.12 -m venv .venv` | `python3 -m venv .venv` |
| `.venv\Scripts\python` | `.venv/bin/python` |
| `curl.exe -L -o ...` | `curl -L -o ...` |
| `notepad Aula_09.py` | `nano Aula_09.py` |
| Porta `"COM5"` | Porta `"/dev/ttyUSB0"` (Linux) ou `"/dev/cu.usbserial-XXXX"` (macOS) |

No Linux, se der erro de permissão na porta serial, rode uma vez `sudo usermod -a -G dialout $USER` e reinicie o computador.

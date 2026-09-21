#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# INTERLOCK DE EPI - DETECCAO DE OCULOS DE SEGURANCA
# MediaPipe FaceLandmarker (Tasks API) + patch ocular alinhado + MLP
#
# AVISO DE ENGENHARIA:
# Demonstracao didatica. Nao e sistema de seguranca. Intertravamento de maquina
# por presenca de EPI exige avaliacao de risco e arquitetura conforme
# ISO 13849-1 / IEC 62061. Webcam + Python + SO de proposito geral nao tem
# canal redundante nem diagnostico de falha.
#
# LIMITE DE VALIDADE DESTE CLASSIFICADOR (ler antes de usar em aula):
# As features abaixo medem BORDA e TEXTURA na regiao ocular. Elas separam
# "tem armacao" de "nao tem armacao". Elas NAO separam oculos de grau de
# oculos de seguranca, que e exatamente a distincao que um interlock de EPI
# precisa fazer. Se esse for o objetivo, colete oculos de grau como classe
# DANGER e observe a acuracia despencar: esse fracasso e o conteudo da aula.
# Separar os dois tipos exige detector treinado (ver secao YOLO no final).
# =============================================================================

import math
import os
import sys
import time
from collections import deque

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import serial

# --- PARAMETROS ---------------------------------------------------------------

PORTA_ESP32 = "COMX"     #Aqui colocar a porta COM de acordo com o ESP32 ex: COM5
BAUD_RATE = 115200
HEARTBEAT_S = 0.10
MODEL_PATH = "face_landmarker.task"

CAMERA_INDEX = 0
LARGURA_DESEJADA = 1280
ALTURA_DESEJADA = 720
TELA_CHEIA = False
ALTURA_REFERENCIA = 720.0

# Patch ocular canonico. Alinhado por rotacao e escala, o que torna as features
# invariantes a distancia do operador e a inclinacao da cabeca. Era o furo
# principal da versao com crop fixo de 35 px.
PW, PH = 160, 64
ALVO_E = (48.0, 32.0)
ALVO_D = (112.0, 32.0)
IOD_ALVO = ALVO_D[0] - ALVO_E[0]

# Indices do FaceMesh canonico: cantos dos olhos.
IDX_OLHO_E = (33, 133)
IDX_OLHO_D = (362, 263)

MIN_AMOSTRAS = 40
TAXA_GRAVACAO_HZ = 8.0
JANELA_VOTO = 9
VOTOS_PARA_DISPARO = 6
PERDA_ROSTO_S = 0.5

JANELA = "Interlock de EPI"
FONT = cv2.FONT_HERSHEY_SIMPLEX
# cv2.putText com fontes Hershey nao renderiza acentuacao.


# --- SERIAL -------------------------------------------------------------------

class LinkBorda(object):
    """
    So transmite em mudanca de estado ou a cada HEARTBEAT_S. Falha de escrita
    nao derruba o loop. O firmware do ESP32 deve ter watchdog: sem mensagem por
    ~300 ms, assume bloqueio. Sem isso, travar o Python libera a maquina.
    """

    def __init__(self, porta, baud):
        self.porta = porta
        self.conn = None
        self.ultimo_envio = 0.0
        self.ultimo_valor = None
        self.erro = None
        if not porta:
            return
        try:
            self.conn = serial.Serial(porta, baud, timeout=0.1)
            time.sleep(2.0)
        except Exception as exc:
            self.erro = str(exc)

    @property
    def ativo(self):
        return self.conn is not None

    def enviar(self, valor):
        if self.conn is None:
            return
        agora = time.perf_counter()
        mudou = valor != self.ultimo_valor
        venceu = (agora - self.ultimo_envio) > HEARTBEAT_S
        if not mudou and not venceu:
            return
        try:
            self.conn.write(valor)
            self.ultimo_envio = agora
            self.ultimo_valor = valor
        except Exception as exc:
            self.erro = str(exc)
            self.conn = None

    def fechar(self):
        if self.conn is None:
            return
        try:
            self.conn.write(b"D")
            self.conn.close()
        except Exception:
            pass


# --- EXTRACAO DE FEATURES -----------------------------------------------------

def centro(landmarks, par, largura, altura):
    a = landmarks[par[0]]
    b = landmarks[par[1]]
    x = (a.x + b.x) * 0.5 * largura
    y = (a.y + b.y) * 0.5 * altura
    return (x, y)


def matriz_alinhamento(pe, pd):
    """Similaridade que leva os dois centros oculares para posicoes fixas."""
    dx = pd[0] - pe[0]
    dy = pd[1] - pe[1]
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return None, 0.0
    ang = math.degrees(math.atan2(dy, dx))
    escala = IOD_ALVO / dist
    cx = (pe[0] + pd[0]) * 0.5
    cy = (pe[1] + pd[1]) * 0.5
    M = cv2.getRotationMatrix2D((cx, cy), ang, escala)
    M[0, 2] += (ALVO_E[0] + ALVO_D[0]) * 0.5 - cx
    M[1, 2] += (ALVO_E[1] + ALVO_D[1]) * 0.5 - cy
    return M, dist


CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def canny_auto(img):
    """Limiares derivados da mediana. Limiar fixo 50/100 quebra com iluminacao."""
    mediana = float(np.median(img))
    baixo = int(max(0, 0.66 * mediana))
    alto = int(min(255, 1.33 * mediana))
    if alto <= baixo:
        alto = baixo + 30
    return cv2.Canny(img, baixo, alto)


def densidade(mascara):
    if mascara.size == 0:
        return 0.0
    return float(np.count_nonzero(mascara)) / float(mascara.size)


def extrair_features(patch):
    """
    15 features adimensionais sobre o patch alinhado. Todas normalizadas por
    area ou por energia total, entao nenhuma depende do tamanho do recorte.
    """
    eq = CLAHE.apply(patch)
    bordas = canny_auto(eq)

    roi_e = bordas[8:56, 16:80]
    roi_p = bordas[8:56, 64:96]     # ponte do nariz: aro/haste central
    roi_d = bordas[8:56, 80:144]
    banda_sup = bordas[2:26, 8:152]  # aro superior da armacao
    banda_inf = bordas[38:62, 8:152]

    d_e = densidade(roi_e)
    d_p = densidade(roi_p)
    d_d = densidade(roi_d)
    d_sup = densidade(banda_sup)
    d_inf = densidade(banda_inf)
    razao_sup = d_sup / (d_inf + 1e-6)
    simetria = abs(d_e - d_d)

    gx = cv2.Sobel(eq, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(eq, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    energia = float(np.mean(mag)) + 1e-6
    e_gx = float(np.mean(np.abs(gx))) / energia
    e_gy = float(np.mean(np.abs(gy))) / energia
    razao_g = e_gy / (e_gx + 1e-6)

    ang = np.arctan2(gy, gx)
    ang = np.mod(ang, math.pi)
    bins = np.floor(ang / (math.pi / 4.0)).astype(np.int32)
    bins = np.clip(bins, 0, 3)
    hog = np.zeros(4, dtype=np.float64)
    for k in range(4):
        hog[k] = float(np.sum(mag[bins == k]))
    total = float(np.sum(hog)) + 1e-6
    hog = hog / total

    lap = cv2.Laplacian(eq, cv2.CV_32F)
    nitidez = float(np.var(lap)) / 1000.0

    return [d_e, d_p, d_d, d_sup, d_inf, razao_sup, simetria,
            e_gx, e_gy, razao_g, hog[0], hog[1], hog[2], hog[3], nitidez]


NOMES_FEATURES = ["d_esq", "d_ponte", "d_dir", "d_sup", "d_inf", "razao_sup",
                  "simetria", "e_gx", "e_gy", "razao_g", "hog0", "hog1",
                  "hog2", "hog3", "nitidez"]


def baseline_limiar(features, corte):
    """
    Regra de uma variavel: densidade media de borda na regiao ocular.
    Serve de piso. Se o MLP com 15 features nao superar isto, o ganho do
    modelo nao esta vindo das features, esta vindo de overfitting.
    """
    media = (features[0] + features[2]) * 0.5
    if media < corte:
        return 1      # pouca borda = sem armacao = sem EPI
    return 0


# --- TREINO -------------------------------------------------------------------

def treinar(X, y):
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)

    idx_tr = []
    idx_te = []
    for classe in (0, 1):
        indices = np.where(y == classe)[0]
        corte = int(len(indices) * 0.7)
        idx_tr.extend(indices[:corte].tolist())
        idx_te.extend(indices[corte:].tolist())

    modelo = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(16, 8), activation="relu",
                      alpha=1e-2, max_iter=6000, random_state=42),
    )
    modelo.fit(X[idx_tr], y[idx_tr])

    acc_tr = modelo.score(X[idx_tr], y[idx_tr])
    acc_te = float("nan")
    acc_base = float("nan")
    corte_base = float(np.median(X[idx_tr][:, 0] + X[idx_tr][:, 2]) * 0.5)

    if idx_te:
        acc_te = modelo.score(X[idx_te], y[idx_te])
        pred = []
        for linha in X[idx_te]:
            pred.append(baseline_limiar(linha, corte_base))
        acc_base = float(np.mean(np.asarray(pred) == y[idx_te]))

    return modelo, acc_tr, acc_te, acc_base, corte_base


# --- HUD ----------------------------------------------------------------------

def painel(frame, linhas, x, y, largura, esc):
    passo = int(22 * esc)
    altura = passo * len(linhas) + int(14 * esc)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + largura, y + altura), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.62, frame, 0.38, 0, frame)
    cv2.rectangle(frame, (x, y), (x + largura, y + altura), (70, 70, 70), 1)
    cursor = y + int(26 * esc)
    for texto, cor in linhas:
        cv2.putText(frame, texto, (x + int(10 * esc), cursor), FONT,
                    0.5 * esc, cor, max(1, int(esc)), cv2.LINE_AA)
        cursor += passo


def barra(frame, x, y, largura, fracao, cor, esc):
    altura = max(6, int(10 * esc))
    cv2.rectangle(frame, (x, y), (x + largura, y + altura), (60, 60, 60), 1)
    cheio = int(largura * min(1.0, fracao))
    if cheio > 1:
        cv2.rectangle(frame, (x + 1, y + 1), (x + cheio, y + altura - 1), cor, -1)


def texto_centralizado(frame, texto, y, escala, cor, espessura):
    (tw, _), _ = cv2.getTextSize(texto, FONT, escala, espessura)
    cv2.putText(frame, texto, (int((frame.shape[1] - tw) / 2), y), FONT,
                escala, cor, espessura, cv2.LINE_AA)


def colar_miniatura(frame, patch, bordas, esc):
    """Mostra o patch alinhado e o mapa de bordas. Depuracao visual na aula."""
    escala = max(1, int(2 * esc))
    vis_p = cv2.cvtColor(cv2.resize(patch, (PW * escala, PH * escala)), cv2.COLOR_GRAY2BGR)
    vis_b = cv2.cvtColor(cv2.resize(bordas, (PW * escala, PH * escala)), cv2.COLOR_GRAY2BGR)
    empilhado = np.vstack([vis_p, vis_b])
    h, w = empilhado.shape[0], empilhado.shape[1]
    x0 = frame.shape[1] - w - int(12 * esc)
    y0 = int(70 * esc)
    if y0 + h < frame.shape[0] and x0 > 0:
        frame[y0:y0 + h, x0:x0 + w] = empilhado
        cv2.rectangle(frame, (x0, y0), (x0 + w, y0 + h), (90, 90, 90), 1)
        cv2.putText(frame, "patch alinhado / bordas", (x0, y0 - int(6 * esc)),
                    FONT, 0.45 * esc, (180, 180, 180), 1, cv2.LINE_AA)


# --- PERSISTENCIA -------------------------------------------------------------

def salvar_csv(X, y):
    nome = "epi_dataset_%s.csv" % time.strftime("%Y%m%d_%H%M%S")
    dados = np.column_stack([np.asarray(X), np.asarray(y)])
    cabecalho = ",".join(NOMES_FEATURES + ["rotulo"])
    np.savetxt(nome, dados, delimiter=",", header=cabecalho, comments="", fmt="%.6f")
    return nome


def carregar_csvs():
    X = []
    y = []
    arquivos = []
    for nome in sorted(os.listdir(".")):
        if nome.startswith("epi_dataset_") and nome.endswith(".csv"):
            dados = np.loadtxt(nome, delimiter=",", skiprows=1)
            if dados.ndim == 1:
                dados = dados.reshape(1, -1)
            X.extend(dados[:, :-1].tolist())
            y.extend(dados[:, -1].astype(int).tolist())
            arquivos.append(nome)
    return X, y, arquivos


# --- CAMERA -------------------------------------------------------------------

def abrir_camera():
    backend = cv2.CAP_ANY
    if sys.platform.startswith("win"):
        backend = cv2.CAP_DSHOW
    cap = cv2.VideoCapture(CAMERA_INDEX, backend)
    if not cap.isOpened():
        return None, 0, 0
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, LARGURA_DESEJADA)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTURA_DESEJADA)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))


def aplicar_tela_cheia(ligado):
    modo = cv2.WINDOW_NORMAL
    if ligado:
        modo = cv2.WINDOW_FULLSCREEN
    cv2.setWindowProperty(JANELA, cv2.WND_PROP_FULLSCREEN, modo)


# --- PROGRAMA -----------------------------------------------------------------

def main():
    link = LinkBorda(PORTA_ESP32, BAUD_RATE)
    if PORTA_ESP32 and not link.ativo:
        print("[ERRO] Falha de comunicacao de borda: %s" % link.erro)
        sys.exit(1)

    try:
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        detector = vision.FaceLandmarker.create_from_options(options)
    except Exception as exc:
        print("[ERRO CRITICO] Falha ao carregar '%s': %s" % (MODEL_PATH, exc))
        sys.exit(1)

    cap, largura, altura = abrir_camera()
    if cap is None:
        print("[ERRO CRITICO] Nenhuma camera no indice %d." % CAMERA_INDEX)
        sys.exit(1)
    print("[VIDEO] resolucao efetiva %dx%d" % (largura, altura))

    escala_hud = altura / ALTURA_REFERENCIA
    cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(JANELA, largura, altura)
    tela_cheia = TELA_CHEIA
    aplicar_tela_cheia(tela_cheia)

    estado = "COLETA"
    X_dataset = []
    y_dataset = []
    modelo = None
    metricas = None
    corte_base = 0.05

    gravando = None
    ultima_gravacao = 0.0

    votos = deque(maxlen=JANELA_VOTO)
    bloqueio_travado = False
    ultimo_rosto = 0.0

    t0 = time.perf_counter()
    fps_hist = deque(maxlen=30)
    t_anterior = t0

    print("\n--- COLETA DE DADOS (EPI) ---")
    print("S = liga/desliga gravacao COM OCULOS DE SEGURANCA")
    print("D = liga/desliga gravacao SEM OCULOS")
    print("T treinar | C limpar | G salvar CSV | L carregar CSVs | F tela cheia | Q sair\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        altura, largura = frame.shape[0], frame.shape[1]
        agora = time.perf_counter()
        fps_hist.append(1.0 / max(1e-3, agora - t_anterior))
        t_anterior = agora

        cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        resultado = detector.detect_for_video(mp_image, int((agora - t0) * 1000.0))

        rosto_ok = False
        features = None
        iod = 0.0

        if resultado.face_landmarks:
            marcas = resultado.face_landmarks[0]
            pe = centro(marcas, IDX_OLHO_E, largura, altura)
            pd = centro(marcas, IDX_OLHO_D, largura, altura)
            M, iod = matriz_alinhamento(pe, pd)
            if M is not None and iod > 25.0:   # rosto muito longe = patch sem informacao
                patch = cv2.warpAffine(cinza, M, (PW, PH), flags=cv2.INTER_LINEAR)
                features = extrair_features(patch)
                rosto_ok = True
                ultimo_rosto = agora
                bordas = canny_auto(CLAHE.apply(patch))
                colar_miniatura(frame, patch, bordas, escala_hud)
                cv2.circle(frame, (int(pe[0]), int(pe[1])), 3, (255, 0, 0), -1)
                cv2.circle(frame, (int(pd[0]), int(pd[1])), 3, (255, 0, 0), -1)
                cv2.line(frame, (int(pe[0]), int(pe[1])), (int(pd[0]), int(pd[1])),
                         (255, 0, 0), 1)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("f"):
            tela_cheia = not tela_cheia
            aplicar_tela_cheia(tela_cheia)

        # ------------------------------------------------------------------
        if estado == "COLETA":
            if key == ord("s"):
                if gravando == 0:
                    gravando = None
                else:
                    gravando = 0
            elif key == ord("d"):
                if gravando == 1:
                    gravando = None
                else:
                    gravando = 1
            elif key == ord("c"):
                X_dataset = []
                y_dataset = []
                gravando = None
            elif key == ord("g"):
                if y_dataset:
                    print("[DADOS] %d amostras salvas em %s"
                          % (len(y_dataset), salvar_csv(X_dataset, y_dataset)))
            elif key == ord("l"):
                Xc, yc, arquivos = carregar_csvs()
                if arquivos:
                    X_dataset.extend(Xc)
                    y_dataset.extend(yc)
                    print("[DADOS] %d amostras carregadas de %d arquivo(s): %s"
                          % (len(yc), len(arquivos), ", ".join(arquivos)))

            n_com = y_dataset.count(0)
            n_sem = y_dataset.count(1)
            pronto = n_com >= MIN_AMOSTRAS and n_sem >= MIN_AMOSTRAS

            if key == ord("t"):
                if not pronto:
                    print("[ERRO] Colete ao menos %d amostras de cada classe." % MIN_AMOSTRAS)
                else:
                    gravando = None
                    print("\n[IA] Treinando com %d amostras..." % len(y_dataset))
                    modelo, acc_tr, acc_te, acc_base, corte_base = treinar(X_dataset, y_dataset)
                    metricas = (acc_tr, acc_te, acc_base)
                    print("[IA] treino=%.3f  holdout=%.3f  limiar simples=%.3f"
                          % (acc_tr, acc_te, acc_base))
                    if acc_tr - acc_te > 0.15:
                        print("[IA] Gap treino-holdout alto: overfitting. Colete mais "
                              "variacao de pose, iluminacao e PESSOAS diferentes.")
                    votos.clear()
                    bloqueio_travado = False
                    estado = "INFERENCIA"

            if gravando is not None and rosto_ok:
                if (agora - ultima_gravacao) > (1.0 / TAXA_GRAVACAO_HZ):
                    X_dataset.append(features)
                    y_dataset.append(gravando)
                    ultima_gravacao = agora

            n_com = y_dataset.count(0)
            n_sem = y_dataset.count(1)
            pronto = n_com >= MIN_AMOSTRAS and n_sem >= MIN_AMOSTRAS

            texto_centralizado(frame, "MODO COLETA - EPI OCULAR", int(36 * escala_hud),
                               0.8 * escala_hud, (255, 255, 0), max(1, int(2 * escala_hud)))

            instrucoes = [
                ("COMO TREINAR CORRETAMENTE:", (255, 255, 255)),
                ("1. S = gravando COM oculos de seguranca.", (0, 255, 0)),
                ("2. D = gravando SEM oculos.", (0, 120, 255)),
                ("3. Em CADA classe, varie: distancia (0,5 a 1,5 m),", (200, 200, 200)),
                ("   giro e inclinacao da cabeca, e a iluminacao.", (200, 200, 200)),
                ("4. Colete com PESSOAS DIFERENTES. Com um rosto so,", (200, 200, 200)),
                ("   a rede aprende o rosto, nao o oculos.", (200, 200, 200)),
                ("5. Oculos de grau: grave como SEM (D) se o alvo e EPI.", (120, 200, 255)),
                ("   Se a acuracia cair, e o limite real do metodo.", (120, 200, 255)),
                ("C limpar  G salvar  L carregar  F tela cheia  Q sair", (150, 150, 150)),
            ]
            painel(frame, instrucoes, int(10 * escala_hud), altura - int(252 * escala_hud),
                   int(470 * escala_hud), escala_hud)

            status = [
                ("COM OCULOS (S): %3d / %d" % (n_com, MIN_AMOSTRAS), (0, 255, 0)),
                ("SEM OCULOS (D): %3d / %d" % (n_sem, MIN_AMOSTRAS), (0, 120, 255)),
            ]
            painel(frame, status, int(10 * escala_hud), int(55 * escala_hud),
                   int(300 * escala_hud), escala_hud)
            barra(frame, int(20 * escala_hud), int(107 * escala_hud), int(270 * escala_hud),
                  n_com / float(MIN_AMOSTRAS), (0, 255, 0), escala_hud)
            barra(frame, int(20 * escala_hud), int(122 * escala_hud), int(270 * escala_hud),
                  n_sem / float(MIN_AMOSTRAS), (0, 120, 255), escala_hud)

            if gravando is not None:
                rotulo = "COM OCULOS"
                cor = (0, 255, 0)
                if gravando == 1:
                    rotulo = "SEM OCULOS"
                    cor = (0, 120, 255)
                aviso = "GRAVANDO %s" % rotulo
                if not rosto_ok:
                    aviso = "GRAVANDO %s - ROSTO NAO DETECTADO" % rotulo
                    cor = (0, 0, 255)
                cv2.putText(frame, aviso, (int(12 * escala_hud), int(150 * escala_hud)),
                            FONT, 0.6 * escala_hud, cor, max(1, int(2 * escala_hud)),
                            cv2.LINE_AA)

            if pronto:
                cor_pisca = (0, 255, 255)
                if int(agora * 2) % 2 == 1:
                    cor_pisca = (0, 170, 190)
                texto_centralizado(frame, "PRESSIONE  T  PARA TREINAR", int(84 * escala_hud),
                                   0.95 * escala_hud, cor_pisca, max(1, int(2 * escala_hud)))
            else:
                texto_centralizado(frame, "Faltam %d COM e %d SEM para liberar o T"
                                   % (max(0, MIN_AMOSTRAS - n_com), max(0, MIN_AMOSTRAS - n_sem)),
                                   int(84 * escala_hud), 0.62 * escala_hud,
                                   (200, 200, 200), max(1, int(escala_hud)))

            link.enviar(b"D")

        # ------------------------------------------------------------------
        else:
            predicao = 1
            if rosto_ok:
                predicao = int(modelo.predict([features])[0])
                votos.append(predicao)
            elif (agora - ultimo_rosto) > PERDA_ROSTO_S:
                votos.append(1)      # sem operador visivel = bloqueio

            if sum(votos) >= VOTOS_PARA_DISPARO:
                bloqueio_travado = True

            if key == ord("r"):
                bloqueio_travado = False
                votos.clear()
            elif key == ord("e"):
                estado = "COLETA"
                gravando = None

            if bloqueio_travado:
                cv2.rectangle(frame, (0, 0), (largura - 1, altura - 1), (0, 0, 255),
                              max(4, int(6 * escala_hud)))
                texto_centralizado(frame, "FALTA EPI - MAQUINA BLOQUEADA",
                                   int(52 * escala_hud), 0.95 * escala_hud, (0, 0, 255),
                                   max(2, int(3 * escala_hud)))
                texto_centralizado(frame, "R para rearmar apos verificacao humana",
                                   int(82 * escala_hud), 0.55 * escala_hud, (0, 0, 255),
                                   max(1, int(escala_hud)))
                link.enviar(b"D")
            elif not rosto_ok:
                texto_centralizado(frame, "AGUARDANDO OPERADOR", int(52 * escala_hud),
                                   0.9 * escala_hud, (255, 255, 0), max(1, int(2 * escala_hud)))
                link.enviar(b"D")
            else:
                texto_centralizado(frame, "EPI DETECTADO - OPERACAO LIBERADA",
                                   int(52 * escala_hud), 0.9 * escala_hud, (0, 255, 0),
                                   max(1, int(2 * escala_hud)))
                link.enviar(b"S")

            base = 0
            if features is not None:
                base = baseline_limiar(features, corte_base)

            linhas = [("MODO INFERENCIA", (255, 255, 255))]
            if metricas:
                linhas.append(("treino=%.2f  holdout=%.2f  limiar=%.2f" % metricas,
                               (170, 170, 255)))
            if features is not None:
                linhas.append(("d_esq=%.3f  d_ponte=%.3f  d_dir=%.3f"
                               % (features[0], features[1], features[2]), (200, 200, 200)))
                linhas.append(("MLP: %d    limiar simples: %d" % (predicao, base),
                               (200, 200, 200)))
            linhas.append(("IOD = %.0f px   votos bloqueio: %d/%d"
                           % (iod, sum(votos), JANELA_VOTO), (200, 200, 200)))
            linhas.append(("R rearmar  E voltar a coleta  F tela cheia  Q sair",
                           (150, 150, 150)))
            painel(frame, linhas, int(10 * escala_hud), altura - int(196 * escala_hud),
                   int(500 * escala_hud), escala_hud)

        fps = 0.0
        if fps_hist:
            fps = sum(fps_hist) / len(fps_hist)
        serial_txt = "serial: offline"
        cor_serial = (140, 140, 140)
        if link.ativo:
            serial_txt = "serial: %s" % PORTA_ESP32
            cor_serial = (0, 255, 0)
        elif link.erro:
            serial_txt = "serial: FALHOU (%s)" % link.erro[:28]
            cor_serial = (0, 0, 255)
        cv2.putText(frame, "%dx%d  %.0f fps" % (largura, altura, fps),
                    (largura - int(200 * escala_hud), altura - int(14 * escala_hud)),
                    FONT, 0.5 * escala_hud, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, serial_txt, (int(12 * escala_hud), altura - int(14 * escala_hud)),
                    FONT, 0.5 * escala_hud, cor_serial, 1, cv2.LINE_AA)

        cv2.imshow(JANELA, frame)
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    link.fechar()


if __name__ == "__main__":
    main()

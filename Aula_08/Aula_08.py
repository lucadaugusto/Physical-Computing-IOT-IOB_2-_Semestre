#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# CERCA VIRTUAL INDUSTRIAL - COLETA E INTERLOCK PREDITIVO (MediaPipe Tasks API)
#
# AVISO DE ENGENHARIA (ler antes de usar em qualquer bancada real):
# Isto e uma DEMONSTRACAO didatica. Nao e protecao de maquina. Protecao de
# maquina exige dispositivo certificado (cortina de luz tipo 4, scanner de area)
# com categoria e Performance Level definidos por ISO 13849-1 / IEC 62061.
# Webcam + USB + Python + SO de proposito geral nao tem canal redundante, nao
# tem diagnostico de falha e nao tem tempo de resposta deterministico.
# =============================================================================

import math
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

PORTA_ESP32 = "COMX"     # ex.: "COM5" ou "/dev/ttyUSB0"; None = modo offline
BAUD_RATE = 115200
HEARTBEAT_S = 0.10
MODEL_PATH = "hand_landmarker.task"

# --- Tela ---
CAMERA_INDEX = 0
LARGURA_DESEJADA = 1280       # a camera NEGOCIA; o valor efetivo e lido de volta
ALTURA_DESEJADA = 720
TELA_CHEIA = False            # tecla F alterna em runtime
ALTURA_REFERENCIA = 720.0     # o HUD foi dimensionado nesta altura e escala a partir dela

# --- Zona de risco ---
# Fracao da ALTURA da imagem, nao pixels fixos. Com raio fixo em px, trocar a
# resolucao mudava o significado de d/R e invalidava silenciosamente qualquer
# dataset gravado antes. Era um furo da versao anterior.
FRACAO_RAIO = 0.28

MIN_AMOSTRAS = 30
TAXA_GRAVACAO_HZ = 10.0
TAU_VELOCIDADE = 0.12         # constante de tempo do filtro, em segundos
PERDA_DETECCAO_S = 0.30

JANELA_VOTO = 7
VOTOS_PARA_DISPARO = 5

JANELA = "Supervisao Cyber-Fisica"
FONT = cv2.FONT_HERSHEY_SIMPLEX
# cv2.putText com fontes Hershey nao renderiza acentuacao. Todo texto de HUD
# neste arquivo e intencionalmente sem acento.


# --- CAMADA SERIAL ------------------------------------------------------------

class LinkBorda(object):
    """
    Envia o estado ao ESP32. So transmite em mudanca de estado ou a cada
    HEARTBEAT_S, e falha de escrita nao derruba o loop de visao.
    O firmware deve implementar watchdog: sem mensagem por ~300 ms, assume
    PERIGO por conta propria. Sem isso, travar o Python deixa a maquina ligada.
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
            self.conn.write(b"D")     # fail-safe: sai deixando o interlock ativo
            self.conn.close()
        except Exception:
            pass


# --- CINEMATICA ---------------------------------------------------------------

class Cinematica(object):
    """
    Features adimensionais: d/R e velocidade radial em raios por segundo, com
    sinal (aproximar positivo). O filtro usa constante de tempo, nao alfa fixo,
    porque alfa fixo muda o comportamento do filtro quando o fps cai; um modelo
    treinado a 30 fps se comportaria diferente a 12 fps.
    """

    def __init__(self, raio):
        self.raio = float(raio)
        self.dist_anterior = None
        self.t_anterior = None
        self.v_filtrada = 0.0

    def reset(self):
        self.dist_anterior = None
        self.t_anterior = None
        self.v_filtrada = 0.0

    def atualizar(self, distancia_px, agora):
        d_norm = distancia_px / self.raio
        if self.dist_anterior is None:
            self.dist_anterior = distancia_px
            self.t_anterior = agora
            self.v_filtrada = 0.0
            return d_norm, 0.0

        delta_t = agora - self.t_anterior
        if delta_t < 1e-4:
            delta_t = 1e-4

        v_bruta = (self.dist_anterior - distancia_px) / delta_t / self.raio
        alpha = 1.0 - math.exp(-delta_t / TAU_VELOCIDADE)
        self.v_filtrada = alpha * v_bruta + (1.0 - alpha) * self.v_filtrada
        self.dist_anterior = distancia_px
        self.t_anterior = agora
        return d_norm, self.v_filtrada


def baseline_geometrico(d_norm, v_norm):
    """
    Regra explicita, sem aprendizado. Existe para a pergunta honesta em sala:
    o MLP ganha disso? Com duas features e 60 amostras, frequentemente nao.
    """
    if d_norm < 1.0:
        return 1
    if d_norm < 1.6 and v_norm > 0.8:
        return 1
    return 0


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
    preenchido = int(largura * min(1.0, fracao))
    if preenchido > 1:
        cv2.rectangle(frame, (x + 1, y + 1), (x + preenchido, y + altura - 1), cor, -1)


def texto_centralizado(frame, texto, y, escala, cor, espessura):
    (tw, _), _ = cv2.getTextSize(texto, FONT, escala, espessura)
    x = int((frame.shape[1] - tw) / 2)
    cv2.putText(frame, texto, (x, y), FONT, escala, cor, espessura, cv2.LINE_AA)


# --- TREINO -------------------------------------------------------------------

def treinar(X, y):
    """
    StandardScaler no pipeline e split TEMPORAL, nao aleatorio: frames
    consecutivos sao quase identicos e um split embaralhado poe vizinhos nos
    dois lados, devolvendo acuracia inflada.
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)

    idx_treino = []
    idx_teste = []
    for classe in (0, 1):
        indices = np.where(y == classe)[0]
        corte = int(len(indices) * 0.7)
        idx_treino.extend(indices[:corte].tolist())
        idx_teste.extend(indices[corte:].tolist())

    modelo = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(8, 4), activation="relu",
                      max_iter=4000, random_state=42),
    )
    modelo.fit(X[idx_treino], y[idx_treino])

    acc_treino = modelo.score(X[idx_treino], y[idx_treino])
    acc_teste = float("nan")
    acc_base = float("nan")
    if idx_teste:
        acc_teste = modelo.score(X[idx_teste], y[idx_teste])
        pred_base = []
        for linha in X[idx_teste]:
            pred_base.append(baseline_geometrico(linha[0], linha[1]))
        acc_base = float(np.mean(np.asarray(pred_base) == y[idx_teste]))

    return modelo, acc_treino, acc_teste, acc_base


# --- CAMERA -------------------------------------------------------------------

def abrir_camera():
    backend = cv2.CAP_ANY
    if sys.platform.startswith("win"):
        backend = cv2.CAP_DSHOW      # MSMF demora a abrir e resiste a trocar resolucao
    cap = cv2.VideoCapture(CAMERA_INDEX, backend)
    if not cap.isOpened():
        return None, 0, 0
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, LARGURA_DESEJADA)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTURA_DESEJADA)
    cap.set(cv2.CAP_PROP_FPS, 30)
    largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cap, largura, altura


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
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        detector = vision.HandLandmarker.create_from_options(options)
    except Exception as exc:
        print("[ERRO CRITICO] Falha ao carregar '%s': %s" % (MODEL_PATH, exc))
        sys.exit(1)

    cap, largura, altura = abrir_camera()
    if cap is None:
        print("[ERRO CRITICO] Nenhuma camera disponivel no indice %d." % CAMERA_INDEX)
        sys.exit(1)

    print("[VIDEO] resolucao pedida %dx%d, efetiva %dx%d"
          % (LARGURA_DESEJADA, ALTURA_DESEJADA, largura, altura))
    if largura != LARGURA_DESEJADA or altura != ALTURA_DESEJADA:
        print("[VIDEO] A camera negou a resolucao pedida e escolheu a mais proxima "
              "que ela suporta. O HUD e o raio se ajustam sozinhos.")

    raio_risco = int(FRACAO_RAIO * altura)
    escala_hud = altura / ALTURA_REFERENCIA
    print("[VIDEO] raio da zona de risco = %d px (%.0f%% da altura)"
          % (raio_risco, FRACAO_RAIO * 100))

    cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(JANELA, largura, altura)
    tela_cheia = TELA_CHEIA
    aplicar_tela_cheia(tela_cheia)

    estado = "COLETA"
    X_dataset = []
    y_dataset = []
    modelo = None
    metricas = None

    gravando = None
    ultima_gravacao = 0.0

    cinematica = Cinematica(raio_risco)
    ultima_deteccao = 0.0
    votos = deque(maxlen=JANELA_VOTO)
    interlock_travado = False

    t0 = time.perf_counter()
    fps_hist = deque(maxlen=30)
    t_frame_anterior = t0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        altura, largura = frame.shape[0], frame.shape[1]
        agora = time.perf_counter()

        fps_hist.append(1.0 / max(1e-3, agora - t_frame_anterior))
        t_frame_anterior = agora

        centro = (int(largura / 2), int(altura - raio_risco / 3))
        cv2.circle(frame, centro, raio_risco, (0, 0, 255), max(2, int(2 * escala_hud)))

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        resultado = detector.detect_for_video(mp_image, int((agora - t0) * 1000.0))

        mao_detectada = False
        d_norm = 0.0
        v_norm = 0.0

        if resultado.hand_landmarks:
            mao_detectada = True
            ultima_deteccao = agora
            pulso = resultado.hand_landmarks[0][0]
            px, py = int(pulso.x * largura), int(pulso.y * altura)
            cv2.circle(frame, (px, py), int(12 * escala_hud), (255, 255, 0), -1)
            cv2.circle(frame, (px, py), int(18 * escala_hud), (0, 255, 255), 2)
            cv2.line(frame, (px, py), centro, (90, 90, 90), 1)

            distancia_px = math.sqrt((centro[0] - px) ** 2 + (centro[1] - py) ** 2)
            d_norm, v_norm = cinematica.atualizar(distancia_px, agora)
        else:
            if (agora - ultima_deteccao) > PERDA_DETECCAO_S:
                cinematica.reset()

        key = cv2.waitKey(1) & 0xFF

        if key == ord("f"):
            tela_cheia = not tela_cheia
            aplicar_tela_cheia(tela_cheia)

        # ------------------------------------------------------------------
        # ESTADO: COLETA
        # ------------------------------------------------------------------
        if estado == "COLETA":
            n_seguro = y_dataset.count(0)
            n_perigo = y_dataset.count(1)
            pronto = n_seguro >= MIN_AMOSTRAS and n_perigo >= MIN_AMOSTRAS

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
                    nome = "dataset_%s.csv" % time.strftime("%Y%m%d_%H%M%S")
                    dados = np.column_stack([np.asarray(X_dataset), np.asarray(y_dataset)])
                    np.savetxt(nome, dados, delimiter=",", header="d_norm,v_norm,rotulo",
                               comments="", fmt="%.6f")
                    print("[DADOS] %d amostras salvas em %s" % (len(y_dataset), nome))
            elif key == ord("t"):
                if not pronto:
                    print("[ERRO] Colete ao menos %d amostras de cada classe." % MIN_AMOSTRAS)
                else:
                    gravando = None
                    print("\n[IA] Treinando com %d amostras..." % len(y_dataset))
                    modelo, acc_tr, acc_te, acc_base = treinar(X_dataset, y_dataset)
                    metricas = (acc_tr, acc_te, acc_base)
                    print("[IA] acuracia treino=%.3f  holdout=%.3f  regra geometrica=%.3f"
                          % (acc_tr, acc_te, acc_base))
                    if acc_base >= acc_te:
                        print("[IA] A regra geometrica empatou ou superou a rede. "
                              "Com duas features linearmente separaveis isso e esperado.")
                    votos.clear()
                    interlock_travado = False
                    estado = "INFERENCIA"

            if gravando is not None and mao_detectada:
                if (agora - ultima_gravacao) > (1.0 / TAXA_GRAVACAO_HZ):
                    X_dataset.append([d_norm, v_norm])
                    y_dataset.append(gravando)
                    ultima_gravacao = agora

            n_seguro = y_dataset.count(0)
            n_perigo = y_dataset.count(1)
            pronto = n_seguro >= MIN_AMOSTRAS and n_perigo >= MIN_AMOSTRAS

            texto_centralizado(frame, "MODO COLETA DE DADOS", int(36 * escala_hud),
                               0.8 * escala_hud, (255, 255, 0), max(1, int(2 * escala_hud)))

            instrucoes = [
                ("COMO TREINAR CORRETAMENTE:", (255, 255, 255)),
                ("1. Tecla S = liga/desliga gravacao SEGURA.", (0, 255, 0)),
                ("   Mao fora do circulo, movimentos lentos,", (170, 220, 170)),
                ("   e tambem SAINDO da zona (afastando).", (170, 220, 170)),
                ("2. Tecla D = liga/desliga gravacao PERIGO.", (0, 120, 255)),
                ("   Mao entrando no circulo e aproximacao", (170, 190, 220)),
                ("   rapida, mesmo ainda de fora.", (170, 190, 220)),
                ("3. Varie distancia e velocidade. Dataset so", (200, 200, 200)),
                ("   com extremos gera fronteira ruim.", (200, 200, 200)),
                ("4. Mantenha as duas classes equilibradas.", (200, 200, 200)),
                ("C = limpar  G = salvar CSV  F = tela cheia  Q = sair", (150, 150, 150)),
            ]
            painel(frame, instrucoes, int(10 * escala_hud),
                   altura - int(272 * escala_hud), int(430 * escala_hud), escala_hud)

            status = [
                ("SAFE  (S): %3d / %d" % (n_seguro, MIN_AMOSTRAS), (0, 255, 0)),
                ("DANGER(D): %3d / %d" % (n_perigo, MIN_AMOSTRAS), (0, 120, 255)),
            ]
            painel(frame, status, int(10 * escala_hud), int(55 * escala_hud),
                   int(260 * escala_hud), escala_hud)
            barra(frame, int(20 * escala_hud), int(107 * escala_hud),
                  int(230 * escala_hud), n_seguro / float(MIN_AMOSTRAS), (0, 255, 0), escala_hud)
            barra(frame, int(20 * escala_hud), int(122 * escala_hud),
                  int(230 * escala_hud), n_perigo / float(MIN_AMOSTRAS), (0, 120, 255), escala_hud)

            if gravando is not None:
                rotulo = "SAFE"
                cor = (0, 255, 0)
                if gravando == 1:
                    rotulo = "DANGER"
                    cor = (0, 120, 255)
                aviso = "GRAVANDO %s" % rotulo
                if not mao_detectada:
                    aviso = "GRAVANDO %s - MAO NAO DETECTADA" % rotulo
                    cor = (0, 0, 255)
                cv2.circle(frame, (largura - int(40 * escala_hud), int(40 * escala_hud)),
                           int(10 * escala_hud), cor, -1)
                (tw, _), _ = cv2.getTextSize(aviso, FONT, 0.6 * escala_hud, 2)
                cv2.putText(frame, aviso, (largura - int(60 * escala_hud) - tw,
                                           int(46 * escala_hud)),
                            FONT, 0.6 * escala_hud, cor, max(1, int(2 * escala_hud)),
                            cv2.LINE_AA)

            if pronto:
                cor_pisca = (0, 255, 255)
                if int(agora * 2) % 2 == 1:
                    cor_pisca = (0, 170, 190)
                texto_centralizado(frame, "PRESSIONE  T  PARA TREINAR",
                                   int(84 * escala_hud), 0.95 * escala_hud, cor_pisca,
                                   max(1, int(2 * escala_hud)))
            else:
                faltam_s = max(0, MIN_AMOSTRAS - n_seguro)
                faltam_d = max(0, MIN_AMOSTRAS - n_perigo)
                texto_centralizado(frame, "Faltam %d SAFE e %d DANGER para liberar o T"
                                   % (faltam_s, faltam_d), int(84 * escala_hud),
                                   0.62 * escala_hud, (200, 200, 200), max(1, int(escala_hud)))

            link.enviar(b"D")

        # ------------------------------------------------------------------
        # ESTADO: INFERENCIA
        # ------------------------------------------------------------------
        else:
            predicao = 0
            if mao_detectada:
                predicao = int(modelo.predict([[d_norm, v_norm]])[0])
                votos.append(predicao)
            else:
                votos.append(0)

            if sum(votos) >= VOTOS_PARA_DISPARO:
                interlock_travado = True

            if key == ord("r"):
                interlock_travado = False
                votos.clear()
            elif key == ord("e"):
                estado = "COLETA"
                gravando = None

            if interlock_travado:
                cv2.rectangle(frame, (0, 0), (largura - 1, altura - 1), (0, 0, 255),
                              max(4, int(6 * escala_hud)))
                texto_centralizado(frame, "!!! INTERLOCK ATIVADO !!!", int(52 * escala_hud),
                                   1.1 * escala_hud, (0, 0, 255), max(2, int(3 * escala_hud)))
                texto_centralizado(frame, "R para rearmar", int(82 * escala_hud),
                                   0.6 * escala_hud, (0, 0, 255), max(1, int(escala_hud)))
                link.enviar(b"D")
            elif not mao_detectada:
                texto_centralizado(frame, "STANDBY", int(52 * escala_hud), 1.0 * escala_hud,
                                   (255, 255, 0), max(1, int(2 * escala_hud)))
                link.enviar(b"S")
            else:
                texto_centralizado(frame, "OPERACAO SEGURA", int(52 * escala_hud),
                                   1.0 * escala_hud, (0, 255, 0), max(1, int(2 * escala_hud)))
                link.enviar(b"S")

            base = baseline_geometrico(d_norm, v_norm)
            divergencia = "iguais"
            if base != predicao:
                divergencia = "DIVERGEM"

            linhas = [
                ("MODO INFERENCIA", (255, 255, 255)),
                ("d/R = %+.2f    v = %+.2f R/s" % (d_norm, v_norm), (200, 200, 200)),
                ("MLP: %d    regra geometrica: %d    (%s)" % (predicao, base, divergencia),
                 (200, 200, 200)),
                ("votos perigo: %d/%d" % (sum(votos), JANELA_VOTO), (200, 200, 200)),
                ("R = rearmar  E = voltar a coleta  F = tela cheia  Q = sair", (150, 150, 150)),
            ]
            if metricas:
                linhas.insert(1, ("treino=%.2f  holdout=%.2f  regra=%.2f"
                                  % metricas, (170, 170, 255)))
            painel(frame, linhas, int(10 * escala_hud), altura - int(196 * escala_hud),
                   int(490 * escala_hud), escala_hud)

        # rodape comum
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

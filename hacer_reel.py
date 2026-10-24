"""Pasos 2 y 3: tu voz clonada narra el guion y se arma el video vertical.

Uso:
    .venv/Scripts/python hacer_reel.py --voz mi_voz.mp4 --autor "Su nombre" --fuente "BCRP"
        --tts modelos/Qwen3-TTS-12Hz-0.6B-Base

Lee salidas/guion.json (ya revisado por una persona) y escribe en salidas/:
reel.mp4, reel.srt, portada.png y posts.md.
"""

import argparse
import json
import re
import subprocess

import jiwer
import numpy as np
import soundfile
import torch
from faster_whisper import WhisperModel
from imageio_ffmpeg import get_ffmpeg_exe
from num2words import num2words
from PIL import Image, ImageDraw, ImageFont
from qwen_tts import Qwen3TTSModel

ANCHO = 1080
ALTO = 1920
CUADROS_POR_SEGUNDO = 30
MARGEN = 90

FONDO = (28, 26, 23)
CREMA = (245, 240, 232)
NARANJA = (240, 140, 60)
GRIS = (150, 145, 138)
CAJA = (48, 45, 41)

FUENTES = "C:/Windows/Fonts/"
FUENTE_CIFRA = ImageFont.truetype(FUENTES + "seguibl.ttf", 250)
FUENTE_ETIQUETA = ImageFont.truetype(FUENTES + "segoeuib.ttf", 64)
FUENTE_CABECERA = ImageFont.truetype(FUENTES + "segoeuib.ttf", 38)
FUENTE_SUBTITULO = ImageFont.truetype(FUENTES + "segoeuib.ttf", 60)
FUENTE_PIE = ImageFont.truetype(FUENTES + "segoeui.ttf", 32)

# Más del 15 % de palabras mal entendidas por Whisper = la escena se genera de nuevo.
# Con 25 % se colaba una escena que se había saltado "dos mil veintiséis y".
ERROR_MAXIMO = 0.15
INTENTOS = 4
# En español la B y la V suenan igual: sin esta pista, Whisper escribe "VCRP".
PALABRAS_ESPERADAS = "BCRP PBI setiembre"
# Errores de Whisper que vimos en la prueba y que no deben salir en los subtítulos.
CORRECCIONES = {"Líe": "Lee", "Leé": "Lee", "VCRP": "BCRP", "septiembre": "setiembre"}
PAUSA_ENTRE_ESCENAS = 0.35
PALABRAS_POR_SUBTITULO = 4


def numero_en_palabras(coincidencia):
    partes = re.split(r"[.,]", coincidencia.group())
    palabras = []
    for parte in partes:
        palabras.append(num2words(int(parte), lang="es"))
    return " coma ".join(palabras)


def normalizar(texto):
    """Whisper escribe '2,6 %' y el guion dice 'dos coma seis por ciento': los igualamos."""
    texto = texto.lower().replace("%", " por ciento")
    texto = re.sub(r"\d+(?:[.,]\d+)?", numero_en_palabras, texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    return " ".join(texto.split())


def audio_para_whisper(ruta):
    """Whisper espera audio a 16 kHz. Lo convertimos con ffmpeg porque la versión
    nueva de la librería `av` ya no es compatible con faster-whisper."""
    resultado = subprocess.run(
        [ffmpeg, "-v", "error", "-i", ruta, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(resultado.stdout, dtype=np.float32)


def transcribir(whisper, ruta):
    """Devuelve la lista de palabras con su segundo de inicio y de fin."""
    segmentos, _ = whisper.transcribe(audio_para_whisper(ruta), language="es", word_timestamps=True,
                                      hotwords=PALABRAS_ESPERADAS)
    palabras = []
    for segmento in segmentos:
        for palabra in segmento.words:
            texto = palabra.word.strip()
            texto = CORRECCIONES.get(texto, texto)
            # Whisper separa "4" de ",25": los volvemos a unir para que el subtítulo diga "4,25".
            if palabras and texto[0] in ",.%":
                palabras[-1]["texto"] += texto
                palabras[-1]["fin"] = palabra.end
            else:
                palabras.append({"texto": texto, "inicio": palabra.start, "fin": palabra.end})
    return palabras


def partir_en_lineas(dibujo, texto, fuente, ancho_maximo):
    lineas = []
    linea_actual = ""
    for palabra in texto.split():
        prueba = (linea_actual + " " + palabra).strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho_maximo:
            linea_actual = prueba
        else:
            lineas.append(linea_actual)
            linea_actual = palabra
    lineas.append(linea_actual)
    return lineas


def dibujar_fondo_de_escena(escena, numero, total, titulo, autor, fuente):
    """Lo que no cambia durante la escena: cabecera, cifra, etiqueta y pie."""
    imagen = Image.new("RGB", (ANCHO, ALTO), FONDO)
    dibujo = ImageDraw.Draw(imagen)

    # Barra de avance: cuántas escenas van.
    dibujo.rectangle([MARGEN, 250, ANCHO - MARGEN, 256], fill=CAJA)
    avance = MARGEN + (ANCHO - 2 * MARGEN) * numero / total
    dibujo.rectangle([MARGEN, 250, avance, 256], fill=NARANJA)

    dibujo.text((MARGEN, 290), titulo.upper(), font=FUENTE_CABECERA, fill=NARANJA)
    ancho_aviso = dibujo.textlength("Voz generada con IA", font=FUENTE_PIE)
    dibujo.rounded_rectangle([MARGEN, 350, MARGEN + ancho_aviso + 40, 405], radius=12, outline=GRIS, width=2)
    dibujo.text((MARGEN + 20, 356), "Voz generada con IA", font=FUENTE_PIE, fill=CREMA)

    dibujo.text((MARGEN, 560), escena["cifra"], font=FUENTE_CIFRA, fill=CREMA)

    y = 880
    for linea in partir_en_lineas(dibujo, escena["etiqueta"], FUENTE_ETIQUETA, ANCHO - 2 * MARGEN):
        dibujo.text((MARGEN, y), linea, font=FUENTE_ETIQUETA, fill=GRIS)
        y += 80

    dibujo.text((MARGEN, 1500), f"{autor} · Fuente: {fuente}", font=FUENTE_PIE, fill=GRIS)
    return imagen


def dibujar_subtitulo(imagen, palabras, segundo):
    """Muestra el grupo de palabras que se está diciendo; la palabra actual va en naranja."""
    grupo_actual = None
    for inicio_grupo in range(0, len(palabras), PALABRAS_POR_SUBTITULO):
        grupo = palabras[inicio_grupo : inicio_grupo + PALABRAS_POR_SUBTITULO]
        if grupo[0]["inicio"] <= segundo:
            grupo_actual = grupo
    if grupo_actual is None:
        return imagen

    imagen = imagen.copy()
    dibujo = ImageDraw.Draw(imagen)
    texto_completo = " ".join(palabra["texto"] for palabra in grupo_actual)
    fuente = FUENTE_SUBTITULO
    ancho_texto = dibujo.textlength(texto_completo, font=fuente)
    # Si las palabras son largas, achicamos la letra para que no se salga de la zona segura.
    if ancho_texto > ANCHO - 2 * MARGEN - 60:
        fuente = ImageFont.truetype(FUENTES + "segoeuib.ttf", 46)
        ancho_texto = dibujo.textlength(texto_completo, font=fuente)
    x = (ANCHO - ancho_texto) / 2
    dibujo.rounded_rectangle([x - 30, 1250, x + ancho_texto + 30, 1350], radius=20, fill=CAJA)

    for palabra in grupo_actual:
        color = CREMA
        if palabra["inicio"] <= segundo <= palabra["fin"]:
            color = NARANJA
        dibujo.text((x, 1262), palabra["texto"], font=fuente, fill=color)
        x += dibujo.textlength(palabra["texto"] + " ", font=fuente)
    return imagen


def formato_srt(segundos):
    milisegundos = int(segundos * 1000)
    horas, milisegundos = divmod(milisegundos, 3_600_000)
    minutos, milisegundos = divmod(milisegundos, 60_000)
    segundos, milisegundos = divmod(milisegundos, 1000)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d},{milisegundos:03d}"


parser = argparse.ArgumentParser()
parser.add_argument("--voz", required=True, help="tu nota de voz (.m4a, .ogg, .mp4, .wav)")
parser.add_argument("--autor", required=True)
parser.add_argument("--fuente", required=True)
parser.add_argument("--titulo", default="Reporte de Inflación · Set. 2026")
# En Windows bajamos los modelos a modelos/ como archivos normales: la caché de
# Hugging Face usa symlinks y Windows no los permite sin modo desarrollador.
parser.add_argument("--tts", default="modelos/Qwen3-TTS-12Hz-0.6B-Base")
parser.add_argument("--whisper", default="modelos/faster-whisper-small")
parser.add_argument("--guion", default="salidas/guion.json")
parser.add_argument("--reusar-audio", action="store_true",
                    help="usa los salidas/escena_N.wav ya generados y solo rehace el video")
argumentos = parser.parse_args()

ffmpeg = get_ffmpeg_exe()

with open(argumentos.guion, encoding="utf-8") as archivo:
    guion = json.load(archivo)

# --- Tu voz de referencia -------------------------------------------------
whisper = WhisperModel(argumentos.whisper, device="cpu", compute_type="int8")

if not argumentos.reusar_audio:
    print("1/4 Preparando tu voz de referencia...")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", argumentos.voz, "-ac", "1", "-ar", "24000",
                    "salidas/voz_completa.wav"], check=True)
    segmentos, _ = whisper.transcribe(audio_para_whisper("salidas/voz_completa.wav"), language="es")

    # El clon aprende mejor de 15 a 20 segundos limpios que de una grabación larga.
    texto_acumulado = ""
    texto_referencia = ""
    fin_referencia = 0
    for segmento in segmentos:
        if fin_referencia > 0 and segmento.end > 20:
            break
        texto_acumulado += segmento.text
        # Cortamos solo donde termina una oración: si la referencia acaba en "La inflación...",
        # el clon cree que ya dijo esas palabras y se las salta al empezar cada escena.
        if texto_acumulado.strip().endswith("."):
            texto_referencia = texto_acumulado
            fin_referencia = segmento.end

    audio_completo, frecuencia_voz = soundfile.read("salidas/voz_completa.wav")
    recorte = audio_completo[: int((fin_referencia + 0.2) * frecuencia_voz)]
    soundfile.write("salidas/referencia.wav", recorte, frecuencia_voz)
    print(f"   Referencia de {fin_referencia:.1f} s: «{texto_referencia.strip()}»")

    print("2/4 Narrando con tu voz clonada (en CPU tarda unos minutos)...")
    tts = Qwen3TTSModel.from_pretrained(argumentos.tts, device_map="cpu", dtype=torch.float32)
    voz_clonada = tts.create_voice_clone_prompt(ref_audio="salidas/referencia.wav",
                                                ref_text=texto_referencia.strip())

# --- Narración, escena por escena -----------------------------------------
pistas = []
escenas_con_tiempos = []
segundo_actual = 0.3
frecuencia = 24000

for numero, escena in enumerate(guion["escenas"], start=1):
    ruta_escena = f"salidas/escena_{numero}.wav"

    if argumentos.reusar_audio:
        mejor_audio, frecuencia = soundfile.read(ruta_escena)
        mejores_palabras = transcribir(whisper, ruta_escena)
    else:
        mejor_error = 1.0
        for intento in range(1, INTENTOS + 1):
            audios, frecuencia = tts.generate_voice_clone(text=escena["frase"], language="Spanish",
                                                          voice_clone_prompt=voz_clonada)
            soundfile.write(ruta_escena, audios[0], frecuencia)

            # Control: Whisper vuelve a escuchar lo que dijo el clon.
            palabras = transcribir(whisper, ruta_escena)
            lo_que_se_entiende = " ".join(palabra["texto"] for palabra in palabras)
            error = jiwer.wer(normalizar(escena["frase"]), normalizar(lo_que_se_entiende))
            print(f"   Escena {numero}, intento {intento}: {error:.0%} de palabras mal entendidas")

            if error < mejor_error:
                mejor_error = error
                mejor_audio = audios[0]
                mejores_palabras = palabras
            if error <= ERROR_MAXIMO:
                break
        # Guardamos el mejor intento, no el último.
        soundfile.write(ruta_escena, mejor_audio, frecuencia)

    for palabra in mejores_palabras:
        palabra["inicio"] += segundo_actual
        palabra["fin"] += segundo_actual
    duracion = len(mejor_audio) / frecuencia
    escenas_con_tiempos.append({"inicio": segundo_actual, "fin": segundo_actual + duracion,
                                "palabras": mejores_palabras})
    pistas.append(mejor_audio)
    pistas.append(np.zeros(int(PAUSA_ENTRE_ESCENAS * frecuencia)))
    segundo_actual += duracion + PAUSA_ENTRE_ESCENAS

# Silencio al inicio y un segundo al final para que el video no corte en seco.
pistas.insert(0, np.zeros(int(0.3 * frecuencia)))
pistas.append(np.zeros(frecuencia))
narracion = np.concatenate(pistas)
soundfile.write("salidas/reel.wav", narracion, frecuencia)
duracion_total = len(narracion) / frecuencia
print(f"   Narración de {duracion_total:.0f} segundos")

# --- Video ------------------------------------------------------------------
print("3/4 Dibujando el video...")
fondos = []
total_escenas = len(guion["escenas"])
for numero, escena in enumerate(guion["escenas"], start=1):
    fondos.append(dibujar_fondo_de_escena(escena, numero, total_escenas, argumentos.titulo,
                                          argumentos.autor, argumentos.fuente))
fondos[0].save("salidas/portada.png")

# -14 LUFS es el volumen que usan las redes. En una sola pasada ffmpeg se quedaba
# en -15.7, así que primero medimos y luego ajustamos con esa medición.
medicion = subprocess.run(
    [ffmpeg, "-hide_banner", "-i", "salidas/reel.wav",
     "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
    capture_output=True, text=True,
)
salida_ffmpeg = medicion.stderr
volumen = json.loads(salida_ffmpeg[salida_ffmpeg.rfind("{") : salida_ffmpeg.rfind("}") + 1])
filtro_volumen = (
    "loudnorm=I=-14:TP=-1.5:LRA=11:linear=true"
    f":measured_I={volumen['input_i']}:measured_TP={volumen['input_tp']}"
    f":measured_LRA={volumen['input_lra']}:measured_thresh={volumen['input_thresh']}"
    f":offset={volumen['target_offset']}"
)

# H.264 + AAC lo acepta cualquier app.
video = subprocess.Popen(
    [ffmpeg, "-v", "error", "-y",
     "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}",
     "-r", str(CUADROS_POR_SEGUNDO), "-i", "-",
     "-i", "salidas/reel.wav",
     "-af", filtro_volumen, "-ar", "48000",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
     "-c:a", "aac", "-b:a", "192k", "-shortest", "salidas/reel.mp4"],
    stdin=subprocess.PIPE,
)

total_cuadros = int(duracion_total * CUADROS_POR_SEGUNDO)
for cuadro in range(total_cuadros):
    segundo = cuadro / CUADROS_POR_SEGUNDO
    # La escena que se ve es la última que ya empezó.
    indice_escena = 0
    for indice, tiempos in enumerate(escenas_con_tiempos):
        if tiempos["inicio"] <= segundo:
            indice_escena = indice
    palabras = escenas_con_tiempos[indice_escena]["palabras"]
    imagen = dibujar_subtitulo(fondos[indice_escena], palabras, segundo)
    video.stdin.write(imagen.tobytes())

video.stdin.close()
video.wait()

# --- Subtítulos y posts -----------------------------------------------------
print("4/4 Escribiendo reel.srt y posts.md...")
numero_subtitulo = 1
with open("salidas/reel.srt", "w", encoding="utf-8") as archivo:
    for tiempos in escenas_con_tiempos:
        palabras = tiempos["palabras"]
        for inicio_grupo in range(0, len(palabras), PALABRAS_POR_SUBTITULO):
            grupo = palabras[inicio_grupo : inicio_grupo + PALABRAS_POR_SUBTITULO]
            texto = " ".join(palabra["texto"] for palabra in grupo)
            archivo.write(f"{numero_subtitulo}\n")
            archivo.write(f"{formato_srt(grupo[0]['inicio'])} --> {formato_srt(grupo[-1]['fin'])}\n")
            archivo.write(f"{texto}\n\n")
            numero_subtitulo += 1

with open("salidas/posts.md", "w", encoding="utf-8") as archivo:
    archivo.write("# Posts del reel\n\n")
    archivo.write(f"## LinkedIn\n\n{guion['posts']['linkedin']}\n\n")
    archivo.write(f"## X\n\n{guion['posts']['x']}\n\n")
    archivo.write(f"## Instagram\n\n{guion['posts']['instagram']}\n")

print("Listo: salidas/reel.mp4, reel.srt, portada.png y posts.md")

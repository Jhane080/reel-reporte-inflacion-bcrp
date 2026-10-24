"""Paso 1: de un texto largo a un guion de reel, escena por escena.

Uso:
    .venv/Scripts/python guion.py --texto informe.pdf --paginas 8-11 --solo-prompt > prompt.txt
    (pegar prompt.txt en chat.qwen.ai y guardar lo que responda en respuesta.txt)
    .venv/Scripts/python guion.py --texto informe.pdf --paginas 8-11 --respuesta respuesta.txt
"""

import argparse
import json
import re
import sys

from pypdf import PdfReader

INSTRUCCIONES = """Eres guionista de reels de divulgación económica para redes sociales en el Perú.
Convierte el TEXTO de abajo en el guion de un reel vertical de 45 a 55 segundos.

Reglas:
1. Exactamente 6 escenas. Cada escena destaca UNA cifra que aparece tal cual en el texto.
2. "frase" es lo que se dice en voz alta: una o dos oraciones cortas, máximo 22 palabras,
   con los números escritos en palabras (por ejemplo "tres coma cuatro por ciento").
3. "cifra" es el número que se ve en pantalla, copiado tal como aparece en el texto (por ejemplo "3,4 %").
4. "etiqueta" explica la cifra en pantalla en máximo 6 palabras.
5. No agregues causas, consecuencias ni opiniones que el texto no diga. Si el texto dice
   "se proyecta", no escribas "será".
6. La primera escena engancha; la última invita a leer el reporte completo.
7. Además escribe tres posts para acompañar el reel: uno para LinkedIn (máx. 80 palabras),
   uno para X (máx. 260 caracteres) y uno para Instagram (máx. 60 palabras, con 3 hashtags).

Responde SOLO con un JSON válido, sin texto antes ni después, con esta forma:
{
  "escenas": [
    {"frase": "...", "cifra": "...", "etiqueta": "..."}
  ],
  "posts": {"linkedin": "...", "x": "...", "instagram": "..."}
}

TEXTO:
"""


def leer_texto(ruta, paginas):
    """Devuelve el texto del PDF; `paginas` es algo como '8-11' (numeración del PDF)."""
    lector = PdfReader(ruta)
    if paginas:
        inicio, fin = paginas.split("-")
        numeros = range(int(inicio) - 1, int(fin))
    else:
        numeros = range(len(lector.pages))

    partes = []
    for numero in numeros:
        partes.append(lector.pages[numero].extract_text() or "")
    return "\n".join(partes)


def cifra_aparece(cifra, texto):
    """¿La cifra aparece tal cual en el texto? Tolera '3,4 %' frente a '3,4%' o '3.4'."""
    # Nos quedamos solo con el número: el texto puede escribir "%" o "por ciento".
    numero = re.sub(r"[^0-9,.]", "", cifra).strip(",.")
    if not numero:
        return False
    texto_sin_espacios = texto.replace(" ", "")
    variantes = [numero, numero.replace(",", "."), numero.replace(".", ",")]
    for variante in variantes:
        if variante in texto_sin_espacios:
            return True
    return False


def extraer_json(respuesta):
    """El chat a veces envuelve el JSON en ```json ... ```; nos quedamos con lo de adentro."""
    inicio = respuesta.find("{")
    fin = respuesta.rfind("}")
    return json.loads(respuesta[inicio : fin + 1])


parser = argparse.ArgumentParser()
parser.add_argument("--texto", required=True, help="PDF de entrada")
parser.add_argument("--paginas", help="rango de páginas, por ejemplo 8-11")
parser.add_argument("--solo-prompt", action="store_true", help="imprime el prompt y termina")
parser.add_argument("--respuesta", help="archivo con la respuesta copiada del chat")
parser.add_argument("--salida", default="salidas/guion.json")
argumentos = parser.parse_args()

texto = leer_texto(argumentos.texto, argumentos.paginas)

if argumentos.solo_prompt:
    # Forzamos UTF-8 para que las tildes no se rompan al redirigir a prompt.txt en Windows.
    sys.stdout.reconfigure(encoding="utf-8")
    print(INSTRUCCIONES + texto)
    sys.exit()

with open(argumentos.respuesta, encoding="utf-8") as archivo:
    guion = extraer_json(archivo.read())

# Los números se verifican con código; las afirmaciones las verifica una persona.
print(f"Texto de entrada: {len(texto.split())} palabras\n")
palabras_habladas = 0
for numero, escena in enumerate(guion["escenas"], start=1):
    if not cifra_aparece(escena["cifra"], texto):
        escena["cifra"] = "¡¡" + escena["cifra"]
    palabras_habladas += len(escena["frase"].split())
    print(f"{numero}. [{escena['cifra']}] {escena['etiqueta']}")
    print(f"   «{escena['frase']}»\n")

# A unas 2.4 palabras por segundo, que es el ritmo de un reel narrado.
print(f"Duración estimada: {palabras_habladas / 2.4:.0f} segundos")

with open(argumentos.salida, "w", encoding="utf-8") as archivo:
    json.dump(guion, archivo, ensure_ascii=False, indent=2)
print(f"Guardado en {argumentos.salida}. Las cifras con ¡¡ no aparecen tal cual en el texto.")

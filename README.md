# Reporte de Inflación del BCRP en un reel de 44 segundos

Tarea de la sesión 15 (Del texto a tu voz) del curso *Fundamentos de Python para
Ciencias Sociales y Gestión Pública*, Diplomado PUCP 2026.

El Resumen del **Reporte de Inflación de setiembre 2026** del BCRP (páginas 8 a 11,
1,923 palabras) se convirtió en un reel vertical narrado con mi voz clonada, usando
solo modelos abiertos.

| Archivo | Qué es |
|---|---|
| [`salidas/reel.mp4`](salidas/reel.mp4) | El reel: 1080 × 1920, 30 fps, 44 s, -14 LUFS |
| [`salidas/posts.md`](salidas/posts.md) | Posts para LinkedIn, X e Instagram |
| [`salidas/reel.srt`](salidas/reel.srt) | Subtítulos |
| [`salidas/portada.png`](salidas/portada.png) | Portada |
| [`salidas/guion.json`](salidas/guion.json) | Guion final, ya revisado |
| [`respuesta.txt`](respuesta.txt) | Guion original de Qwen, sin tocar |

> Voz generada con IA. Es mi propia voz, clonada con Qwen3-TTS.

## El flujo

1. **Texto largo:** Resumen del Reporte de Inflación (`informe.pdf`).
2. **Guion:** Qwen (chat.qwen.ai) escribe 6 escenas, cada una con una cifra.
   `guion.py` marca con ¡¡ toda cifra que no aparezca tal cual en el texto.
3. **Revisión:** leí el guion contra el reporte y lo corregí (ver abajo).
4. **Mi voz:** Qwen3-TTS-0.6B clona mi voz a partir de una nota de voz de WhatsApp.
   Whisper vuelve a escuchar cada escena y la genera de nuevo si entiende mal más
   del 15 % de las palabras.
5. **Video:** Pillow dibuja los cuadros y ffmpeg arma el MP4 con subtítulos.

## Qué corregí del guion y por qué

Las 6 cifras de Qwen estaban bien: todas aparecen en el reporte. Lo que fallaba era
el **contexto**: a varias frases les faltaba algo, y una cifra sin su año o sin
"del PBI" se puede malinterpretar.

| Escena | Qwen escribió | Problema | Quedó así |
|---|---|---|---|
| 2 | «Se revisa a la baja la proyección de crecimiento del PBI a tres coma dos por ciento.» | No dice el año: parece crecimiento actual. | «Para dos mil veintiséis, la proyección de crecimiento del PBI baja de tres coma cuatro a tres coma dos por ciento.» |
| 5 | «El Directorio decidió mantener la tasa de interés de referencia…» | En un reel nadie sabe qué Directorio. | «El BCRP mantiene su tasa de referencia en cuatro coma veinticinco por ciento desde setiembre de dos mil veinticinco.» |
| 6 | «…déficit fiscal se ubique en uno coma cinco por ciento.» | Falta "del PBI" y el año: el número no se entiende. | «Se proyecta un déficit fiscal de uno coma cinco por ciento del PBI en dos mil veintiséis y dos mil veintisiete. Lee el reporte completo.» |
| Posts | «Lee el informe completo aquí 👇», sin enlace | No había enlace ni aviso de IA. | Enlace al BCRP y «Voz generada con IA» en los tres posts. |

## Qué salió mal con la voz (y cómo se arregló)

- **El clon se comía el inicio de las frases.** Dijo «…anual aumentó» en vez de
  «La inflación interanual aumentó». La grabación de referencia estaba cortada a
  media oración («La inflación…») y el modelo creía que ya había dicho esas
  palabras. Ahora se corta solo donde termina una oración.
- **La escena 6 se saltó «dos mil veintiséis y»** y pasó el control automático
  (24 % de error con un límite de 25 %). La encontré leyendo lo que se escuchó
  contra el guion. Bajé el límite a 15 %.
- **Whisper escribía «VCRP», «septiembre» y «Líe»** en los subtítulos. En español
  la B y la V suenan igual, así que no era error del clon. Se corrige con una lista
  de palabras esperadas y otra de correcciones.

Los números se verifican con código. Las afirmaciones las verifica una persona.

## Cómo replicarlo (Windows, sin GPU)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe qwen-tts faster-whisper pillow imageio-ffmpeg soundfile jiwer num2words pypdf
```

Bajen los modelos a `modelos/`, como archivos normales, porque la caché de Hugging Face
usa symlinks y Windows no los permite:

```bash
.venv/Scripts/python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', local_dir='modelos/faster-whisper-small'); snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-Base', local_dir='modelos/Qwen3-TTS-12Hz-0.6B-Base')"
```

El PDF se descarga a mano desde bcrp.gob.pe, porque la web bloquea las descargas
automáticas. Guárdenlo como `informe.pdf`.

```bash
.venv/Scripts/python guion.py --texto informe.pdf --paginas 8-11 --solo-prompt > prompt.txt
# pegar prompt.txt en chat.qwen.ai y guardar la respuesta en respuesta.txt
.venv/Scripts/python guion.py --texto informe.pdf --paginas 8-11 --respuesta respuesta.txt
# revisar salidas/guion.json contra el PDF
.venv/Scripts/python hacer_reel.py --voz mi_voz.mp4 --autor "Su nombre" --fuente "BCRP"
```

En CPU, la narración tarda unos 15 minutos. Si solo cambian el diseño, agreguen
`--reusar-audio` y el video se rehace en unos 2 minutos, sin volver a narrar.

## Lo que no está en el repo

- **Mi grabación de voz.** La voz es un dato biométrico; solo se usó en mi laptop.
- **El PDF del BCRP y los modelos** (unos 3 GB): se descargan con los pasos de arriba.

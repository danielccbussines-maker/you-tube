# Taxi: bot privado de Telegram para iPhone

Proyecto nuevo: no se pudo recuperar código del chat anterior. Preparado para el repositorio `danielccbussines-maker/you-tube` y un worker de Railway.

**Estado:** preparado para desplegar; no activado ni probado con una cuenta de Telegram real. El 2 de noviembre de 2026 Railway devolvió «Sign ups are currently disabled. Please try again later» al intentar el alta con GitHub. No se ha creado un servicio ni contratado un plan.

## Lo que hace

- `/taxi` envía por Telegram hasta cinco MP3 de la lista de vídeos autorizados. `/taxi 6` comienza en la sexta entrada aprobada. El orden corresponde a la lista aprobada, no a las posiciones originales de YouTube.
- Playlist de referencia: https://www.youtube.com/playlist?list=PLDIoUOhQQPlWc-Kd6TCjTRIl0Z6fSQV0X
- Solo usuarios configurados y chats privados pueden descargar. `/id` está disponible para cualquier usuario en privado, pero solo devuelve su propio ID.
- Sin usuarios autorizados o sin permisos documentados, las descargas están bloqueadas.
- Procesa un lote a la vez. Temporales eliminados al acabar; sin archivo permanente. Cada ejecución vuelve a procesar su lote.
- Límite de 30 minutos por pista, 5 minutos de procesamiento por pista y 45 MB por MP3. Una pista fallida no detiene el lote.

## Pasos personales necesarios

1. En Telegram, abre el BotFather oficial: https://t.me/BotFather. Usa `/newbot`, elige nombre y un usuario terminado en `bot`. Guarda el token de forma privada. **No lo pegues en chats, GitHub, capturas ni archivos del repositorio.** Si ya existe el bot, puedes usarlo; no crees otro innecesariamente.
2. Cuando Railway admita el alta, inicia sesión en https://railway.com/dashboard. Revisa tú cualquier contrato o plan con coste antes de aceptarlo. No se presupone alojamiento gratuito permanente.
3. En Railway: **New Project → Deploy from GitHub repo → danielccbussines-maker/you-tube**. Si no aparece, concede a la integración de Railway acceso solo a este repositorio. Esta autorización de cuenta la completas tú.
4. En el servicio → **Variables**, introduce directamente `TELEGRAM_BOT_TOKEN` y su valor. Añade `TAXI_APPROVALS_JSON` con `[]`. Puedes dejar `ALLOWED_USER_IDS` vacío para obtener primero tu ID: el bot solo responderá a `/id` y no permitirá descargas.
5. Despliega y abre tu bot en Telegram desde el iPhone. Envía `/id`. Copia ese número a `ALLOWED_USER_IDS` en Railway y aplica los cambios. El número es tu ID de usuario, no el token.
6. Comprueba `/start` y `/estado`. `/taxi` debe indicar que no hay pistas autorizadas hasta revisar los permisos.
7. Tras documentar los permisos, actualiza `TAXI_APPROVALS_JSON` como se explica debajo. Envía `/taxi` y guarda cada MP3 desde Telegram → Compartir → Guardar en Archivos.

Railway detecta el Dockerfile e instala ffmpeg. Es un proceso persistente mediante long polling: no necesita dominio público, puerto, webhook ni volumen. Mantén **una réplica**, desactiva Serverless/suspensión si aparece habilitado y evita ejecutar otra copia del mismo bot. El reinicio descarta comandos antiguos pendientes para evitar descargas inesperadas. La configuración solicita cero segundos de solapamiento entre despliegues.

## Autorizar las pistas

No se han comprobado los derechos de esta playlist. La configuración viene vacía y **no descarga la playlist completa ni busca automáticamente vídeos nuevos**. El operador debe revisar cada entrada y conservar la documentación fuera del repositorio. El programa valida los campos, pero no puede comprobar por sí solo la autenticidad o suficiencia legal de un permiso.

En `TAXI_APPROVALS_JSON`, registra una entrada por vídeo revisado, en el orden deseado:

```json
[
  {
    "video_id": "ID_DE_VIDEO",
    "playlist_id": "PLDIoUOhQQPlWc-Kd6TCjTRIl0Z6fSQV0X",
    "rights_permission_ref": "Referencia privada al permiso de los titulares",
    "youtube_permission_ref": "Referencia privada a la autorización de YouTube para este acceso y descarga"
  }
]
```

`ID_DE_VIDEO` es un marcador: sustitúyelo por el ID real de 11 caracteres del vídeo autorizado. No incluyas tokens, documentos privados ni claves en esas referencias. Quita una entrada y redespliega si caduca o se revoca el permiso.

Una playlist pública, comprar una canción, YouTube Premium o una etiqueta Creative Commons no acreditan por sí solos que YouTube permita extraer un MP3 mediante este bot. Sus condiciones restringen descargas y acceso automatizado salvo autorización aplicable del servicio y titulares. Si no tienes esos permisos, deja `[]` y usa los archivos originales entregados legalmente por el titular. No se ofrece ninguna garantía de acceso a vídeos protegidos. El bot no usa cookies de sesión, DRM bypass, proxies ni evasión de bloqueos. YouTube puede rechazar incluso una solicitud autorizada; en ese caso se omite la pista.

Fuentes: [condiciones de YouTube](https://www.youtube.com/static?template=terms), [Dockerfiles en Railway](https://docs.railway.com/builds/dockerfiles), [configuración de Railway](https://docs.railway.com/config-as-code/reference), [Telegram sendAudio](https://core.telegram.org/bots/api#sendaudio).

## Comprobaciones y mantenimiento

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest -v
```

Para ejecución local, instala ffmpeg y configura las mismas variables en tu entorno privado antes de ejecutar `.venv/bin/python bot.py`. No publiques `.env`. Las versiones de dependencias están fijadas y deben actualizarse de forma revisada cuando cambie YouTube. No se han probado descargas reales ni el contenedor de Railway; esas comprobaciones requieren cuenta, token y contenido autorizado.

Los errores visibles y logs omiten URLs de Telegram y detalles de excepciones para evitar revelar tokens. Si se filtra un token, revócalo en BotFather y reemplázalo únicamente en Railway. Si recibes un conflicto de polling, detén cualquier segunda instancia y vuelve a desplegar una sola réplica.

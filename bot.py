"""Private Telegram worker. Download authorization is required per video."""
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

PLAYLIST_ID = "PLDIoUOhQQPlWc-Kd6TCjTRIl0Z6fSQV0X"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
MAX_BYTES = 45_000_000
MAX_SECONDS = 1800
BATCH_SIZE = 5
JOB_LOCK = asyncio.Lock()


def approvals(raw):
    """Fail closed: references must document rights AND platform permission.

    These references are operator-reviewed records, not automatic proof of rights.
    A playlist, a public video or a CC label alone does not grant platform permission.
    """
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) > 500:
        raise ValueError("Invalid approvals list")
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Invalid approval")
        video = item.get("video_id", "")
        if not isinstance(video, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError("Invalid video ID")
        if video in seen or item.get("playlist_id") != PLAYLIST_ID:
            raise ValueError("Duplicate video or different playlist")
        for field in ("rights_permission_ref", "youtube_permission_ref"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Missing permission reference")
        seen.add(video)
    return data


def owner_ids(raw):
    values = {int(value.strip()) for value in raw.split(",") if value.strip()}
    if any(value <= 0 for value in values):
        raise ValueError("Invalid owner ID")
    return values


def allowed(update, owners):
    return bool(update.effective_user and update.effective_chat
                and update.effective_chat.type == "private"
                and update.effective_user.id in owners)


def download(video_id, directory):
    if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Invalid video ID")
    # No arbitrary URLs, cookies, proxies, DRM bypass or dynamically fetched code.
    command = [
        sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
        "--no-progress", "--quiet", "--no-warnings", "--no-cache-dir",
        "--socket-timeout", "20", "--retries", "1", "--fragment-retries", "1",
        "--max-filesize", "45M", "--match-filters", "duration <= 1800 & !is_live",
        "-f", "bestaudio[filesize<45000000]/bestaudio",
        "-x", "--audio-format", "mp3", "--audio-quality", "128K",
        "-o", str(Path(directory) / "audio.%(ext)s"),
        "--", f"https://www.youtube.com/watch?v={video_id}",
    ]
    # Kill the entire process group on timeout (including ffmpeg).
    import signal
    child_env = {key: value for key, value in os.environ.items()
                 if key not in {"TELEGRAM_BOT_TOKEN", "TAXI_APPROVALS_JSON", "ALLOWED_USER_IDS"}}
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True, env=child_env)
    try:
        result = process.wait(timeout=300)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise RuntimeError("Download timeout") from None
    path = Path(directory) / "audio.mp3"
    if result or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise RuntimeError("Download unavailable or too large")
    return path


async def identity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            f"Tu ID de Telegram: {update.effective_user.id}. "
            "Guárdalo en ALLOWED_USER_IDS de Railway. No es el token del bot.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.bot_data["owners"]):
        return
    await update.effective_message.reply_text(
        "Bot privado listo. /taxi envía hasta 5 pistas autorizadas. "
        "/taxi 6 empieza en la sexta pista aprobada. /estado muestra la configuración. "
        "Solo se procesan vídeos con permisos documentados del titular y de YouTube.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if allowed(update, context.bot_data["owners"]):
        await update.effective_message.reply_text(
            f"Pistas autorizadas: {len(context.bot_data['approvals'])}. "
            f"Trabajo en curso: {'sí' if JOB_LOCK.locked() else 'no'}.\n{PLAYLIST_URL}")


async def taxi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context.bot_data["owners"]):
        return
    items = context.bot_data["approvals"]
    if not items:
        await update.effective_message.reply_text(
            "No hay pistas autorizadas. La playlist no acredita permisos. "
            "Antes de descargar, registra autorizaciones individuales en "
            "TAXI_APPROVALS_JSON; consulta el README. No envíes documentos ni tokens al bot.")
        return
    try:
        position = int(context.args[0]) if context.args else 1
        if len(context.args) > 1 or not 1 <= position <= len(items):
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Usa /taxi o /taxi 6, con una posición válida.")
        return
    if JOB_LOCK.locked():
        await update.effective_message.reply_text("Ya hay una descarga en curso. Espera a que termine.")
        return
    async with JOB_LOCK:
        await update.effective_message.reply_text("Procesando el lote autorizado…")
        sent = 0
        batch = items[position - 1:position - 1 + BATCH_SIZE]
        for item in batch:
            try:
                with tempfile.TemporaryDirectory(prefix="taxi-") as directory:
                    path = await asyncio.to_thread(download, item["video_id"], directory)
                    with path.open("rb") as audio:
                        await update.effective_message.reply_audio(
                            audio=audio, filename=f"{item['video_id']}.mp3",
                            title=item["video_id"], write_timeout=120, read_timeout=120)
                    sent += 1
            except Exception:
                # Never echo exception strings: Telegram URLs contain the bot token.
                await update.effective_message.reply_text(
                    f"No se pudo enviar {item['video_id']}: "
                    "puede estar bloqueado, no disponible o superar los límites. "
                    "No se intentará eludir restricciones.")
        following = position + len(batch)
        suffix = f" Siguiente lote: /taxi {following}" if following <= len(items) else " Fin de la lista aprobada."
        await update.effective_message.reply_text(f"Enviadas {sent} de {len(batch)} pistas.{suffix}")


async def errors(update, context):
    logging.error("Telegram operation failed (%s)", type(context.error).__name__)


async def init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Ayuda"), BotCommand("taxi", "Pistas autorizadas"),
        BotCommand("estado", "Estado del bot"), BotCommand("id", "Mi ID de Telegram")])


def main():
    # Only our sanitized errors are logged. No HTTP debug output or tracebacks.
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
    for name in ("httpx", "httpcore", "telegram", "yt_dlp"):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    try:
        token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
        owners = owner_ids(os.environ.get("ALLOWED_USER_IDS", ""))
        records = approvals(os.environ.get("TAXI_APPROVALS_JSON", "[]"))
        app = Application.builder().token(token).concurrent_updates(8).post_init(init).build()
        app.bot_data.update(owners=owners, approvals=records)
        for name, handler in (("id", identity), ("start", start), ("estado", status)):
            app.add_handler(CommandHandler(name, handler))
        app.add_handler(CommandHandler("taxi", taxi))
        app.add_error_handler(errors)
        app.run_polling(drop_pending_updates=True, allowed_updates=["message"])
    except Exception as error:
        logging.error("Bot stopped (%s). Check private service variables.", type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

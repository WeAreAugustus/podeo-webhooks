import hashlib
import hmac
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from flask import request
from flask_restx import Namespace, Resource

from resources.cliq_podeo import notify_rss_podeo, notify_podeo_error
from resources.upload_podeo_videos import (
    smashi_login,
    upload_video_to_smashi,
    login_lovin_backend,
    upload_video_to_lovin_backend,
    lovin_upload,
)
from utils.podcast_lookup import (
    find_cms_show_id,
    find_cms_category_id,
    is_lovin_podcast,
    is_smashi_podcast,
    find_lovin_show_id,
    find_lovin_category_id,
    get_show_title,
    get_poster_image_path,
    PROJECT_ROOT,
)
from utils.s3_utils import S3Client
from utils.logger import logger

import requests

# Characters to replace with dash in video/poster file names (backend-safe and filesystem-safe)
_SANITIZE_CHARS = [' ', '(', ')', '@', '%', '#', '&', '+', '?', '=', '/', '\\', ',', ':' , '-']


def _sanitize_video_filename(title: str) -> str:
    """Build a unique, backend-safe base name: sanitize title and append timestamp."""
    base = str(title) if title else "video"
    for ch in _SANITIZE_CHARS:
        base = base.replace(ch, "-")
    base = re.sub(r"-+", "-", base).strip("-")  # collapse multiple dashes, trim
    if not base:
        base = "video"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{timestamp}"


def _get_local_poster_path(podcast_id) -> str | None:
    """Return poster path from podcast object's image_path only."""
    if podcast_id is None:
        return None
    # Use image_path from podcast object (relative to project root) only.
    rel_path = get_poster_image_path(podcast_id)
    if rel_path:
        # Normalize: JSON has paths like "images/lovin/File.jpg"; resolve against project root.
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel_path))
        if os.path.isfile(abs_path):
            return abs_path
        logger.debug("image_path from JSON not found at %s (project_root=%s)", abs_path, PROJECT_ROOT)
    return None

# Optional: only if using Lovin upload
try:
    from resources.lovin_auth import login as lovin_login
except ImportError:
    lovin_login = None

ns = Namespace("Podeo", path="/webhook", description="Podeo webhook")
CLIENT_ID = (os.getenv("PODEO_CLIENT_ID", "") or "").strip().strip('"')
CLIENT_SECRET = (os.getenv("PODEO_CLIENT_SECRET", "") or "").strip().strip('"')
if not CLIENT_ID or not CLIENT_SECRET:
    logger.warning("Podeo webhook signature auth disabled: PODEO_CLIENT_ID or PODEO_CLIENT_SECRET not set")


@ns.route("/podeo")
class PodeoWebhook(Resource):
    _event_queue = queue.Queue()
    _worker_started = False
    _worker_lock = threading.Lock()

    @classmethod
    def _worker_loop(cls):
        while True:
            event_type, event_data = cls._event_queue.get()
            try:
                cls().handle_events(event_type, event_data)
            except Exception as e:
                logger.exception("Queue worker failed while handling event '%s': %s", event_type, e)
            finally:
                cls._event_queue.task_done()

    @classmethod
    def _ensure_worker_started(cls):
        with cls._worker_lock:
            if cls._worker_started:
                return
            worker = threading.Thread(target=cls._worker_loop, name="podeo-webhook-worker", daemon=True)
            worker.start()
            cls._worker_started = True
            logger.info("Podeo webhook worker started (single-threaded queue mode)")

    def upload_mp3(self, event_data):
        temp_paths = []
        try:
            job_id = uuid.uuid4().hex[:10]
            mp3_url = event_data.get("mp3_url", "")
            title = event_data.get("name", "")
            # API may send podcasts_id or podcast_id; normalize to int for lookups
            podcast_id = event_data.get("podcasts_id") or event_data.get("podcast_id")
            if podcast_id is not None:
                try:
                    podcast_id = int(podcast_id)
                except (TypeError, ValueError):
                    pass

            response = requests.get(mp3_url)
            input_mp3_path = os.path.join(PROJECT_ROOT, f"input_{job_id}.mp3")
            temp_paths.append(input_mp3_path)
            with open(input_mp3_path, "wb") as f:
                f.write(response.content)
            logger.info("MP3 downloaded")

            # Strict behavior: use image_path from this request's podcast object only.
            local_poster = _get_local_poster_path(podcast_id)
            if not local_poster:
                logger.warning(
                    "Podcast %s has no valid image_path file in object; skipping upload to avoid wrong image reuse",
                    podcast_id,
                )
                return ""
            image_path = local_poster
            logger.info("Using object poster %s for podcast %s", local_poster, podcast_id)

            audio_path = input_mp3_path
            output_path = os.path.join(PROJECT_ROOT, f"output_{job_id}.mp4")
            temp_paths.append(output_path)
            ffmpeg_exe = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
            if not ffmpeg_exe:
                logger.error(
                    "ffmpeg not found. Install ffmpeg and add it to PATH, or set FFMPEG_PATH in .env to the full path to ffmpeg.exe"
                )
                return ""
            # Strip quotes if present (sometimes .env files have them)
            ffmpeg_exe = ffmpeg_exe.strip('"\'')
            # Resolve to absolute path so Windows CreateProcess finds it reliably
            ffmpeg_exe = os.path.abspath(ffmpeg_exe)
            if not os.path.isfile(ffmpeg_exe):
                logger.error(
                    "ffmpeg executable not found at %s. Fix FFMPEG_PATH in .env or install ffmpeg on PATH.",
                    ffmpeg_exe,
                )
                return ""
            logger.info("Using ffmpeg: %s", ffmpeg_exe)
            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1", "-framerate", "2", "-i", image_path,
                "-i", audio_path,
                "-vf", "scale=1280:-2", "-c:v", "libx264",
                "-tune", "stillimage", "-preset", "ultrafast", "-crf", "35",
                "-r", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
                "-shortest", output_path
            ]
            subprocess.run(cmd, check=True)
            logger.info("MP4 created: %s", output_path)
            time.sleep(2)

            sanitized_base = _sanitize_video_filename(title)
            video_filename = sanitized_base + ".mp4"
            s3_client = S3Client()
            with open(output_path, "rb") as f:
                file_bytes = f.read()
            uploaded_url = s3_client.upload_file(
                file_bytes, video_filename, "podcasts", "video/mp4"
            )
            logger.info("MP4 uploaded: %s", uploaded_url)

            # Poster URL for API: always upload this request's object image to S3.
            poster_url_for_api = None
            if local_poster and os.path.isfile(local_poster):
                try:
                    import io
                    poster_bytes = None
                    use_jpeg = True
                    try:
                        from PIL import Image
                        with Image.open(local_poster) as img:
                            rgb = img.convert("RGB")
                            buf = io.BytesIO()
                            rgb.save(buf, format="JPEG", quality=90)
                            poster_bytes = buf.getvalue()
                    except ImportError:
                        with open(local_poster, "rb") as pf:
                            poster_bytes = pf.read()
                        ext = (os.path.splitext(local_poster)[1] or ".png").lstrip(".").lower()
                        use_jpeg = ext in ("jpg", "jpeg")
                        if not use_jpeg:
                            logger.warning("Pillow not installed: uploading poster as %s (install Pillow to send as JPG)", ext)
                    except Exception as conv_e:
                        logger.warning("PIL conversion failed, using original bytes: %s", conv_e)
                        with open(local_poster, "rb") as pf:
                            poster_bytes = pf.read()
                        use_jpeg = (os.path.splitext(local_poster)[1] or "").lower() in (".jpg", ".jpeg")
                    if poster_bytes:
                        poster_base_name = f"{sanitized_base}_{job_id}_poster"
                        if use_jpeg:
                            poster_name = poster_base_name + ".jpg"
                            content_type = "image/jpeg"
                        else:
                            ext = (os.path.splitext(local_poster)[1] or ".png").lstrip(".")
                            poster_name = poster_base_name + "." + ext
                            content_type = "image/" + ("jpeg" if ext.lower() in ("jpg", "jpeg") else ext.lower())
                        poster_key = s3_client.upload_file(poster_bytes, poster_name, "podcasts", content_type)
                        if poster_key:
                            poster_url_for_api = "https://cdn.smashi.tv/" + poster_key
                            logger.info("Poster uploaded to S3 as JPG, using URL for API: %s", poster_url_for_api)
                except Exception as e:
                    logger.warning("Failed to upload local poster to S3: %s", e)

            if not poster_url_for_api:
                logger.warning("No poster URL generated for podcast %s; skipping upload", podcast_id)
                return ""

            podcast_id = event_data.get("podcasts_id")
            if podcast_id is None:
                logger.info("No podcasts_id in event data, skipping upload")
                return ""

            if is_lovin_podcast(podcast_id) and lovin_login:
                # lovin_username = os.environ.get("email_lovin_username")
                # lovin_pass = os.environ.get("email_lovin_password")
                # token = lovin_login("https://lovin.co/cairo/graphql", lovin_username, lovin_pass)
                # lovin_upload(token, event_data, "https://cdn.smashi.tv/" + uploaded_url)
                # lovin_backend_email = os.getenv("email_lovin_username")
                # lovin_backend_password = os.getenv("email_lovin_password")


                lovin_cms_show_id = find_lovin_show_id(podcast_id)
                if not lovin_cms_show_id:
                    logger.info("No CMS show ID found for Podeo ID: %s", podcast_id)

                lovin_cms_category_id = find_lovin_category_id(podcast_id)
                if not lovin_cms_category_id:
                    logger.info("No CMS Category ID found for Podeo ID: %s", podcast_id)


                token = login_lovin_backend("mahmoud.s@augustusmedia.com", "Passw@@rd#123")
                upload_video_to_lovin_backend(
                    output_path, token, title, lovin_cms_show_id, lovin_cms_category_id,
                    event_data.get("description", ""), poster_url_for_api,
                    poster_path=local_poster,
                    video_filename=video_filename,
                )
                logger.info("Uploaded video to Lovin (podcast_id=%s)", podcast_id)
            
            elif is_smashi_podcast(podcast_id):
                token = smashi_login(os.getenv("email_smashi_username"), os.getenv("email_smashi_password"))
                if not token:
                    logger.warning("Smashi login failed")
                    return ""
                cms_id = find_cms_show_id(podcast_id)
                if not cms_id:
                    logger.info("No CMS show ID found for Podeo ID: %s", podcast_id)
                    return ""
                cms_category_id = find_cms_category_id(podcast_id)
                if not cms_category_id:
                    logger.info("No CMS Category ID found for Podeo ID: %s", podcast_id)
                    return ""
                success = upload_video_to_smashi(
                    output_path, token, title, cms_id, cms_category_id,
                    event_data.get("description", ""), poster_url_for_api,
                    video_filename=video_filename,
                )
                if success:
                    logger.info("Uploaded video to Smashi (podcast_id=%s)", podcast_id)
                else:
                    logger.warning("Smashi upload failed")
            else:
                logger.info(
                    "Podcast id %s not in podcasts_lovin.json or podcasts_smashi.json, skipping upload",
                    podcast_id,
                )
        except Exception as e:
            logger.exception("Error uploading MP3: %s", e)
        finally:
            for path in temp_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as cleanup_err:
                    logger.warning("Failed cleaning temporary file %s: %s", path, cleanup_err)
        return ""

    def handle_events(self, event_type, event_data):
        title = event_data.get("name", "")
        if event_type == "episode_updated":
            pass
        elif event_type == "episode_removed":
            pass
        elif event_type == "episode_created":
            pass
        elif event_type == "episode_distributed":
            notify_rss_podeo(f"Episode distributed: {title}", event_data, "podeowebhooks")
            self.upload_mp3(event_data)
        elif event_type == "podcast_updated":
            pass
        elif event_type == "podcast_removed":
            pass
        elif event_type == "podcast_distributed":
            pass

    def post(self):
        received_token = (request.headers.get("token") or request.headers.get("Token") or "").strip()
        received_date = (request.headers.get("date") or request.headers.get("Date") or "").strip()
        if not received_token or not received_date:
            return {"error": "Missing headers"}, 400

        signature_string = f"{CLIENT_SECRET}_{CLIENT_ID}__{received_date}"
        expected_hash = hashlib.sha256(signature_string.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected_hash, received_token):
            error_detail = (
                f"*Invalid signature (403)*\n"
                f"• received_token: `{received_token}`\n"
                f"• received_date: `{received_date}`\n"
                f"• expected_hash: `{expected_hash}`\n"
                f"• headers: `{dict(request.headers)}`"
            )
            logger.warning(
                "Webhook 403 Invalid signature: headers=%s received_token=%s received_date=%s expected_hash=%s",
                dict(request.headers),
                received_token,
                received_date,
                expected_hash,
            )
            return {"error": "Invalid signature" , "error_detail": error_detail}, 403

        try:
            payload = request.json
            logger.info("Webhook payload: %s", json.dumps(payload, ensure_ascii=False))
            event_type = payload.get("event")
            event_data = payload.get("data")
            logger.info("Received Podeo event: %s", event_type)

            self._ensure_worker_started()
            self._event_queue.put((event_type, event_data))
            return {"status": "queued"}, 200
        except Exception as e:
            logger.exception("Error processing webhook: %s", e)
            notify_podeo_error("Podeo webhook error (500)", str(e))
            return {"error": "Internal server error"}, 500
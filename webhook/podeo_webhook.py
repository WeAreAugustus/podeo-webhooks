import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import threading
import time
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

# Use same project root as data loader (where data/ and images/ live)
_IMAGES_BASE = os.path.join(PROJECT_ROOT, "images")
_ALLOWED_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Characters to replace with dash in video/poster file names (backend-safe and filesystem-safe)
_SANITIZE_CHARS = [' ', '(', ')', '@', '%', '#', '&', '+', '?', '=', '/', '\\']


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
    """If this podcast has an image (from object image_path or folder lookup), return its path; else None."""
    if podcast_id is None:
        return None
    # Prefer image_path from podcast object (relative to project root)
    rel_path = get_poster_image_path(podcast_id)
    if rel_path:
        # Normalize: JSON has "images/lovin/File.jpg"; resolve against project root (same as data loader)
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel_path))
        if os.path.isfile(abs_path):
            return abs_path
        logger.debug("image_path from JSON not found at %s (project_root=%s)", abs_path, PROJECT_ROOT)

    if is_lovin_podcast(podcast_id):
        folder = os.path.join(_IMAGES_BASE, "lovin")
    elif is_smashi_podcast(podcast_id):
        folder = os.path.join(_IMAGES_BASE, "smashi")
    else:
        return None
    if not os.path.isdir(folder):
        return None

    # Lovin: match by show title (e.g. "The Lovin Cairo Show" -> "Lovin Cairo.jpg")
    if is_lovin_podcast(podcast_id):
        show_title = get_show_title(podcast_id) or ""
        match_key = show_title.replace("The Lovin ", "").replace("The Lovin' ", "").replace(" Show", "").strip()
        if match_key:
            match_key = "Lovin " + match_key
            match_lower = match_key.lower()
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith(_ALLOWED_IMAGE_EXTS):
                    continue
                stem = os.path.splitext(name)[0]
                if match_lower in stem.lower():
                    return os.path.join(folder, name)

    # Smashi: match by show title (e.g. "The Smashi Gaming Show" -> "smashi_gaming.png")
    if is_smashi_podcast(podcast_id):
        show_title = get_show_title(podcast_id) or ""
        # "The Smashi Gaming Show" -> "gaming"; "Smashi Entertainment Show" -> "entertainment"
        match_key = (
            show_title.replace("The Smashi ", "").replace("Smashi ", "").replace(" Show", "").strip()
        )
        if match_key:
            match_lower = match_key.lower()
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith(_ALLOWED_IMAGE_EXTS):
                    continue
                stem = os.path.splitext(name)[0]  # e.g. smashi_gaming
                if match_lower in stem.lower() or ("smashi_" + match_lower) in stem.lower():
                    return os.path.join(folder, name)

    # Fallback: image.png, image.jpg, or first image in folder
    for name in ("image.png", "image.jpg", "image.jpeg", "image.webp"):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(_ALLOWED_IMAGE_EXTS):
            return os.path.join(folder, name)
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
    def upload_mp3(self, event_data):
        try:
            mp3_url = event_data.get("mp3_url", "")
            poster_url = event_data.get("image_url", "")
            title = event_data.get("name", "")
            # API may send podcasts_id or podcast_id; normalize to int for lookups
            podcast_id = event_data.get("podcasts_id") or event_data.get("podcast_id")
            if podcast_id is not None:
                try:
                    podcast_id = int(podcast_id)
                except (TypeError, ValueError):
                    pass

            response = requests.get(mp3_url)
            input_mp3_path = os.path.join(PROJECT_ROOT, "input.mp3")
            with open(input_mp3_path, "wb") as f:
                f.write(response.content)
            logger.info("MP3 downloaded")

            # Use image only from image_path in podcast object when set; use API image_url only when object has no image_path
            poster_image_path = os.path.join(PROJECT_ROOT, "poster_image")
            default_image_path = os.path.join(PROJECT_ROOT, "image.png")
            image_path = default_image_path if os.path.isfile(default_image_path) else "image.png"
            has_image_path_in_object = bool(get_poster_image_path(podcast_id))
            local_poster = _get_local_poster_path(podcast_id)
            if local_poster:
                image_path = local_poster
                shutil.copy2(local_poster, poster_image_path)
                logger.info("Using local poster from %s for podcast %s", local_poster, podcast_id)
            elif has_image_path_in_object:
                # Object has image_path but file missing: use default, do not use API image_url
                if os.path.isfile(default_image_path):
                    shutil.copy2(default_image_path, poster_image_path)
                    image_path = default_image_path
                logger.info("Podcast has image_path but file not found, using default image (not API image_url)")
            elif poster_url:
                try:
                    img_resp = requests.get(poster_url, timeout=10)
                    img_resp.raise_for_status()
                    with open(poster_image_path, "wb") as img_f:
                        img_f.write(img_resp.content)
                    image_path = poster_image_path
                    logger.info("Poster image downloaded from payload: %s", poster_url)
                except Exception as e:
                    logger.warning(
                        "Failed to download poster image from %s, falling back to default image.png: %s",
                        poster_url,
                        e,
                    )

            audio_path = input_mp3_path
            output_path = os.path.join(PROJECT_ROOT, "output.mp4")
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

            # Poster URL for API: use our image (upload to S3) when object has image_path or we used local;
            # use API image_url only when object has no image_path and we downloaded from API.
            poster_url_for_api = poster_url if not has_image_path_in_object else None
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
                        if use_jpeg:
                            poster_name = str(title).replace(" ", "_") + "_poster.jpg"
                            content_type = "image/jpeg"
                        else:
                            ext = (os.path.splitext(local_poster)[1] or ".png").lstrip(".")
                            poster_name = sanitized_base + "_poster." + ext
                            content_type = "image/" + ("jpeg" if ext.lower() in ("jpg", "jpeg") else ext.lower())
                        poster_key = s3_client.upload_file(poster_bytes, poster_name, "podcasts", content_type)
                        if poster_key:
                            poster_url_for_api = "https://cdn.smashi.tv/" + poster_key
                            logger.info("Poster uploaded to S3 as JPG, using URL for API: %s", poster_url_for_api)
                except Exception as e:
                    logger.warning("Failed to upload local poster to S3, using API poster_url: %s", e)
            elif has_image_path_in_object and os.path.isfile(poster_image_path):
                # Object has image_path but file was missing; we used default image - upload it to S3 (do not use API image_url)
                try:
                    import io
                    poster_bytes = None
                    try:
                        from PIL import Image
                        with Image.open(poster_image_path) as img:
                            rgb = img.convert("RGB")
                            buf = io.BytesIO()
                            rgb.save(buf, format="JPEG", quality=90)
                            poster_bytes = buf.getvalue()
                    except (ImportError, Exception):
                        with open(poster_image_path, "rb") as pf:
                            poster_bytes = pf.read()
                    if poster_bytes:
                        poster_name = sanitized_base + "_poster.jpg"
                        poster_key = s3_client.upload_file(poster_bytes, poster_name, "podcasts", "image/jpeg")
                        if poster_key:
                            poster_url_for_api = "https://cdn.smashi.tv/" + poster_key
                            logger.info("Poster (default) uploaded to S3, using URL for API: %s", poster_url_for_api)
                except Exception as e:
                    logger.warning("Failed to upload default poster to S3: %s", e)

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
                    poster_path=poster_image_path if os.path.isfile(poster_image_path) else None,
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
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    if os.path.exists(output_path):
                        os.remove(output_path)
                else:
                    logger.warning("Smashi upload failed")
            else:
                logger.info(
                    "Podcast id %s not in podcasts_lovin.json or podcasts_smashi.json, skipping upload",
                    podcast_id,
                )
        except Exception as e:
            logger.exception("Error uploading MP3: %s", e)
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

            threading.Thread(
                target=self.handle_events,
                args=(event_type, event_data),
                daemon=True
            ).start()
            return {"status": "received"}, 200
        except Exception as e:
            logger.exception("Error processing webhook: %s", e)
            notify_podeo_error("Podeo webhook error (500)", str(e))
            return {"error": "Internal server error"}, 500
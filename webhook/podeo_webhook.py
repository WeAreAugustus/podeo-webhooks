import hashlib
import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from flask import request
from flask_restx import Namespace, Resource

from resources.cliq_podeo import notify_rss_podeo
from resources.upload_podeo_videos import (
    smashi_login,
    upload_video_to_smashi,
    login_lovin_backend,
    upload_video_to_lovin_backend,
    lovin_upload,
)
from utils.podcast_lookup import find_cms_show_id, find_cms_category_id, is_lovin_podcast, is_smashi_podcast , find_lovin_show_id , find_lovin_category_id
from utils.s3_utils import S3Client
from utils.logger import logger

import requests

# Optional: only if using Lovin upload
try:
    from resources.lovin_auth import login as lovin_login
except ImportError:
    lovin_login = None

ns = Namespace("Podeo", path="/webhook", description="Podeo webhook")
CLIENT_ID = os.getenv("PODEO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("PODEO_CLIENT_SECRET", "")


@ns.route("/podeo")
class PodeoWebhook(Resource):
    def upload_mp3(self, event_data):
        try:
            mp3_url = event_data.get("mp3_url", "")
            poster_url = event_data.get("image_url", "")
            title = event_data.get("name", "")
            response = requests.get(mp3_url)
            with open("input.mp3", "wb") as f:
                f.write(response.content)
            logger.info("MP3 downloaded")

            # Default fallback image (local file) if download fails or no poster_url
            image_path = "image.png"
            # Try to use the same image as in the payload for the video
            if poster_url:
                try:
                    img_resp = requests.get(poster_url, timeout=10)
                    img_resp.raise_for_status()
                    with open("poster_image", "wb") as img_f:
                        img_f.write(img_resp.content)
                    image_path = "poster_image"
                    logger.info("Poster image downloaded from payload: %s", poster_url)
                except Exception as e:
                    logger.warning(
                        "Failed to download poster image from %s, falling back to default image.png: %s",
                        poster_url,
                        e,
                    )

            audio_path = "input.mp3"
            output_path = "output.mp4"
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

            s3_client = S3Client()
            with open(output_path, "rb") as f:
                file_bytes = f.read()
            uploaded_url = s3_client.upload_file(
                file_bytes, str(title).replace(" ", "_") + ".mp4", "podcasts", "video/mp4"
            )
            logger.info("MP4 uploaded: %s", uploaded_url)

            podcast_id = event_data.get("podcasts_id")
            if podcast_id is None:
                logger.info("No podcasts_id in event data, skipping upload")
                return ""

            if is_lovin_podcast(podcast_id) and lovin_login:
                lovin_username = os.environ.get("email_lovin_username")
                lovin_pass = os.environ.get("email_lovin_password")
                token = lovin_login("https://lovin.co/cairo/graphql", lovin_username, lovin_pass)
                lovin_upload(token, event_data, "https://cdn.smashi.tv/" + uploaded_url)
                lovin_backend_email = os.getenv("email_lovin_username")
                lovin_backend_password = os.getenv("email_lovin_password")


                lovin_cms_show_id = find_lovin_show_id(podcast_id)
                if not lovin_cms_show_id:
                    logger.info("No CMS show ID found for Podeo ID: %s", podcast_id)

                lovin_cms_category_id = find_lovin_category_id(podcast_id)
                if not lovin_cms_category_id:
                    logger.info("No CMS Category ID found for Podeo ID: %s", podcast_id)


                token = login_lovin_backend("mahmoud.s@augustusmedia.com", "Passw@@rd#123")
                upload_video_to_lovin_backend(
                    "output.mp4", token, title,lovin_cms_show_id , lovin_cms_category_id,
                    event_data.get("description", ""), poster_url
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
                    "output.mp4", token, title, cms_id, cms_category_id,
                    event_data.get("description", ""), poster_url
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
            notify_rss_podeo(f"Episode updated: {title}", event_data, "podeowebhooks")
        elif event_type == "episode_removed":
            notify_rss_podeo(f"Episode removed: {title}", event_data, "podeowebhooks")
        elif event_type == "episode_created":
            notify_rss_podeo(f"Episode created: {title}", event_data, "podeowebhooks")
        elif event_type == "episode_distributed":
            notify_rss_podeo(f"Episode distributed: {title}", event_data, "podeowebhooks")
            self.upload_mp3(event_data)
        elif event_type == "podcast_updated":
            notify_rss_podeo(f"Podcast updated: {title}", event_data, "podeowebhooks")
        elif event_type == "podcast_removed":
            notify_rss_podeo(f"Podcast removed: {title}", event_data, "podeowebhooks")
        elif event_type == "podcast_distributed":
            notify_rss_podeo(f"Podcast distributed: {title}", event_data, "podeowebhooks")

    def post(self):
        received_token = request.headers.get("token") or request.headers.get("Token")
        received_date = request.headers.get("date") or request.headers.get("Date")
        if not received_token or not received_date:
            return {"error": "Missing headers"}, 400

        signature_string = f"{CLIENT_SECRET}_{CLIENT_ID}__{received_date}"
        expected_hash = hashlib.sha256(signature_string.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected_hash, received_token):
            return {"error": "Invalid signature"}, 403

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
            return {"error": "Internal server error"}, 500
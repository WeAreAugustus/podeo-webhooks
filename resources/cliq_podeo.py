import logging
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

from utils.podcast_lookup import is_lovin_podcast, is_smashi_podcast

load_dotenv()
logger = logging.getLogger(__name__)

CLIQ_ZAPIKEY = os.environ.get("CLIQ_ZAPIKEY", "")


def notify_rss_podeo(title, json_payload, channel_name):
    try:
        image_url = json_payload.get(
            "image_url",
            "https://podeo.co/wp-content/uploads/2024/09/EmblemBlueSmall.png"
        )
        try:
            brand_message = f"🏷️ *Brand:* {json_payload.get('brand_name')}" if json_payload.get("brand_name") else ""
            podcast_message = f"🎧 *Podcast:* {json_payload.get('podcast_name')}" if json_payload.get("podcast_name") else ""
            episode_message = f"🎙️ *Episode:* {json_payload.get('episode_name')}" if json_payload.get("episode_name") else ""

            audio_url = json_payload.get("mp3_url")
            audio_message = f"🎧 *Audio:* [Listen to episode]({audio_url})" if audio_url else ""

            updated_raw = json_payload.get("updated_at")
            readable_updated = None
            if updated_raw:
                try:
                    if isinstance(updated_raw, str):
                        iso_value = updated_raw.replace("Z", "+00:00") if "Z" in updated_raw else updated_raw
                        parsed_dt = datetime.fromisoformat(iso_value)
                        readable_updated = parsed_dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        readable_updated = str(updated_raw)
                except Exception:
                    readable_updated = updated_raw

            updated_message = f"📅 *Last Updated:* {readable_updated}" if readable_updated else ""
            status_message = f"💬 *Status:* {json_payload.get('text_status')}" if json_payload.get("text_status") else ""
            rss_message = f"🔗 *RSS Feed:* {json_payload.get('rss_feed')}" if json_payload.get("rss_feed") else ""
            last_episode_message = f"🎙️ *Latest Episode Number:* {json_payload.get('last_episode_number')}" if json_payload.get("last_episode_number") else ""
            last_season_message = f"🎬 *Latest Season Number:* {json_payload.get('last_season_number')}" if json_payload.get("last_season_number") else ""

            podcast_id = json_payload.get("podcasts_id")
            if podcast_id is not None:
                if is_lovin_podcast(podcast_id):
                    upload_target_message = "📤 *Upload target:* Lovin"
                elif is_smashi_podcast(podcast_id):
                    upload_target_message = "📤 *Upload target:* Smashi"
                else:
                    upload_target_message = "📤 *Upload target:* —"
            else:
                upload_target_message = ""

            message = f"""
{brand_message}
{podcast_message}
{episode_message}
{audio_message}
{updated_message}
{status_message}
{rss_message}
{last_episode_message}
{last_season_message}
{upload_target_message}
            """.strip()
        except Exception as e:
            message = f"Couldn't parse output\n full json: {str(json_payload)}"
            title = "Error Parsing webhook Data"
            image_url = ""

        headers = {"Content-Type": "application/json"}
        args = {"zapikey": CLIQ_ZAPIKEY}

        url = f"https://cliq.zoho.com/company/837937507/api/v2/channelsbyname/{channel_name}/message"
        payload = {
            "card": {
                "title": title,
                "theme": "modern-inline",
                "thumbnail": image_url,
            },
            "bot": {
                "name": "Podeo Webhooks",
                "image": "https://secure.gravatar.com/avatar/60ed7741ba4020db6132fb8cd0be1835?s=96&d=mm&r=g",
            },
            "text": message,
        }
        response = requests.post(url, json=payload, headers=headers, params=args)
        response.raise_for_status()
        logger.info(f"Cliq webhook sent successfully: {response.json()['message']}")
    except Exception as e:
        logger.error(f"Error sending Cliq webhook: {e}")
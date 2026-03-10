import os
import requests
from datetime import date
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
load_dotenv()


def smashi_login(email: str, password: str) -> str:
    """
    Takes email password of smashi and returns the access token of the user.

    Arguments:
        username: Email of the user.
        password: Password of the user.
    Returns:
    Token(str): Access token of the user will return None of the login failed.
    """
    url = "https://api.smashi.tv/api/v4/auth/login"
    json = {
        "email": email,
        "password": password
    }
    response = requests.post(
        url, json=json)
    if response.status_code == 200:
        token = response.json().get("data").get("accessToken")
        return token
    else:
        return None


def upload_video_to_smashi(video_file_path: str, token: str, title: str, shows_id: int, category_id: int, description: str, poster_url: str, video_filename: str = None) -> bool:
    """
    Takes a video path and token and uploads video to smashi.

    Arguments:
        video_file_path(str): Path of the video to upload.
        token(str): Smashi Access token.
        title(str): Title of the video.
        show_id(in): Show id on smashi.
        category_id(int): Category of the show.
        description(str): Video body.
        poster_url(str): Poster image url.
        video_filename(str): Optional filename for the uploaded video (e.g. sanitized + timestamp). If None, uses title + ".mp4".
    Returns:
        Bool: True for success and false for failure.
    """
    url = "https://api.smashi.tv/api/v4/videos" # production url

    payload = {
        "link": "",
        "title": title,
        "en_title": title,
        "poster_url": poster_url,
        "is_latest": 1,
        "is_featured": 1,
        "body": description,
        "created_at_arabic": date.today(),
        "published_on": date.today(),
        "published_status": 1,
        "shows_id": shows_id,
        "category_id": category_id,
        "is_vertical": 0,
        "is_free": "0",
        "status": "uploaded"
    }

    name_for_file = (video_filename if video_filename else (title + ".mp4"))
    files = [
        ('video_file', (name_for_file, open(video_file_path, 'rb'), 'video/mp4'))
    ]

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.request(
            "POST", url, headers=headers, data=payload, files=files)
        print(response.json())
    except Exception as e:
        import logging
        logging.error(f"Error uploading video to Smashi: {e}")
        return False
    
    response.raise_for_status()
    return response.status_code == 200


def lovin_upload(token, event_data, uploaded_url, city: str = "cairo") -> str:
    uploaded_url = "https://cdn.smashi.tv/"+uploaded_url
    print(uploaded_url)
    url = f"https://lovin.co/{city}/graphql"
    query = f"""
mutation createEpisode {{
    createEpisode(
        input: {{
            content: "{event_data.get("description","")}"
            title: "{event_data.get("name","SMASHI BUSINESS SHOW")}"
            status: PUBLISH
            recordedVideo: "{uploaded_url}"
            recordedVideoThumbnail: "{event_data.get("image_url","")}"
            shows: {{nodes: {{slug: "shows-2025"}}}}
        }}
    ) {{
        episode {{
            slug
            title
            uri
            status
            content
        }}
    }}
}}
"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url=url, headers=headers, json={"query": query})
    print(response.json())
    response.raise_for_status()
    return response.json()


def login_lovin_backend(email: str, password: str) -> str:
    url = "https://api.lovin.co/api/v4/auth/login"
    payload = {
        "email": email,
        "password": password
    }
    response = requests.post(url=url, json=payload)
    print(f"Lovin backend login response: {response.text}")
    
    token = response.json().get("data").get("accessToken")
    return token


def upload_video_to_lovin_backend(video_file_path: str, token: str,
 title: str, shows_id: int, category_id: int,
 description: str, poster_url: str, poster_path: str = None, video_filename: str = None) -> bool:
    """
    Takes a video path and token and uploads video to Lovin backend.

    Arguments:
        video_file_path(str): Path of the video to upload.
        token(str): Lovin Access token.
        title(str): Title of the video.
        shows_id(int): Show id on Lovin.
        category_id(int): Category of the show.
        description(str): Video body.
        poster_url(str): Poster image url (for API payload).
        poster_path(str): Optional path to poster image file. If None, uses poster_image or image.png in CWD.
        video_filename(str): Optional filename for the uploaded video (e.g. sanitized + timestamp). If None, uses title + ".mp4".
    Returns:
        Bool: True for success and false for failure.
    """
    url = "https://api.lovin.co/api/v4/videos"

    payload = {
        "link": "",
        "title": title,
        "en_title": title,
        "poster_url": poster_url,
        "is_latest": 1,
        "is_featured": 1,
        "body": description,
        "created_at_arabic": date.today(),
        "published_on": date.today(),
        "published_status": 1,
        "shows_id": shows_id,
        "category_id": category_id,
        "is_vertical": 0,
        "is_free": "0",
        "status": "uploaded"
    }

    if poster_path and os.path.isfile(poster_path):
        pass
    elif os.path.exists("poster_image"):
        poster_path = "poster_image"
    else:
        poster_path = "image.png"
    ext = os.path.splitext(poster_path)[1].lower()
    poster_content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    name_for_file = (video_filename if video_filename else (title + ".mp4"))
    files = [
        ("video_file", (name_for_file, open(video_file_path, "rb"), "video/mp4")),
        ("poster_file", (os.path.basename(poster_path), open(poster_path, "rb"), poster_content_type)),
    ]

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.request(
        "POST", url, headers=headers, data=payload, files=files)
    print(response.json())
    response.raise_for_status()
    return response.status_code == 200

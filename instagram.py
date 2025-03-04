from util import *
import requests
from secret import API_KEY, INSTAGRAM_ACCOUNT_ID, INSTAGRAM_PASSWORD, ACCESS_TOKEN
import time
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

INSTAGRAM_ACCOUNT_ID = "17841472641873114"  # The IG Business Account ID
ACCESS_TOKEN = "IGAATwznIgZBhFBZAE9GZAmUwZA0hSR1N6SnBZAWGxQQjZATSVBsSTRjV0l4dDA5VnlmejRuU2owaUN2TVNiUXIxam5SQXFmVHFON2V2eWRFUjBfb0dzV1VtWnRqYzBsamZAQZA2p4UWhQakwtYjRSNzBXSnRRQlZAiYkFTZAmUtaUVkalBzSQZDZD"  # Long-lived token
INSTAGRAM_GRAPH_API = "https://graph.instagram.com/v22.0"

def ig_post(image_url, caption):
    """
    Uploads an image to Instagram using Graph API v22.0 by providing a public URL.
    """
    # Step 1: Create Media Container
    url = f"{INSTAGRAM_GRAPH_API}/{INSTAGRAM_ACCOUNT_ID}/media"
    payload = {
        "caption": caption,
        "access_token": ACCESS_TOKEN,
        "media_type": "IMAGE",
        "image_url": image_url
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        media_id = response.json().get("id")
        print(f"Image uploaded successfully! Media ID: {media_id}")

        # Step 2: Publish the uploaded media
        publish_url = f"{INSTAGRAM_GRAPH_API}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        publish_payload = {
            "creation_id": media_id,
            "access_token": ACCESS_TOKEN,
        }

        publish_response = requests.post(publish_url, data=publish_payload)

        if publish_response.status_code == 200:
            print("Post published successfully!")
        else:
            print(f"Publishing failed: {publish_response.json()}")
    else:
        print(f"Upload failed: {response.json()}")

ASAP = False

def wait_until_post_time():
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz)
    # Set target posting time—for example, 8:00 AM CST
    post_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now >= post_time:
        # If it's already past 8 AM today, wait until tomorrow
        post_time += timedelta(days=1)
    sleep_seconds = (post_time - now).total_seconds()
    print(f"Sleeping for {sleep_seconds/3600:.2f} hours until 8 AM CST")
    time.sleep(sleep_seconds)

if __name__ == "__main__":
    while True:
        if not ASAP:
            # Wait until the scheduled posting time, then generate fresh status text
            wait_until_post_time()
            msg1, msg2, msg3 = generate_status_text()
            msg4 = "To access shuttle data, visit the link in our bio. This is an automated message, coded by Dariel Cruz Rodriguez using data from Andrei Thüler's UChicago Shuttles API."
            caption = "\n\n".join([msg1, msg2, msg3, msg4])
            ig_post(make_photo(), caption)
            # pause briefly after posting
            time.sleep(60)
        else:
            # In ASAP mode, generate status text immediately and post
            make_photo()
            msg1, msg2, msg3 = generate_status_text()
            msg4 = "To access shuttle data, visit the link in our bio. This is an automated message, coded by Dariel Cruz Rodriguez using data from Andrei Thüler's UChicago Shuttles API."
            caption = "\n\n".join([msg1, msg2, msg3, msg4])
            ig_post(make_photo(), caption)
            time.sleep(1800)
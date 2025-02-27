from util import *
from secret import API_KEY, BSKY_PASSWORD, BSKY_USERNAME
import time
import pytz
from datetime import datetime, date, timedelta
from atproto import Client

client = Client()
client.login(BSKY_USERNAME, BSKY_PASSWORD)

from atproto import Client, models, client_utils
from secret import BSKY_USERNAME, BSKY_PASSWORD

client = Client()
client.login(BSKY_USERNAME, BSKY_PASSWORD)

def post(message1: str, message2: str, message3: str):
    try:
        # Post the first message (the thread root)
        response1 = client.send_post(message1)
        
        # Create a strong reference for the first post
        root_ref = models.create_strong_ref(response1)
        
        # Post the second message as a reply to the first post
        response2 = client.send_post(
            message2,
            reply_to=models.AppBskyFeedPost.ReplyRef(
                parent=models.create_strong_ref(response1),
                root=root_ref
            )
        )
        
        # Post the third message as a reply to the second post (but still part of the same thread)
        response3 = client.send_post(
            message3,
            reply_to=models.AppBskyFeedPost.ReplyRef(
                parent=models.create_strong_ref(response2),
                root=root_ref
            )
        )

        print("Posted successfully!" if response3 else "Failed to post")
    except Exception as e:
        print(f"Error: {e}")
        raise

ASAP = True  # Set to True to post immediately, for debugging

def wait_until_post_time():
    tz = pytz.timezone("America/Chicago")
    now = datetime.datetime.now(tz)
    # Set target posting time—for example, 8:00 AM CST
    post_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now >= post_time:
        # If it's already past 8 AM today, wait until tomorrow
        post_time += datetime.timedelta(days=1)
    sleep_seconds = (post_time - now).total_seconds()
    print(f"Sleeping for {sleep_seconds/3600:.2f} hours until 8 AM CST")
    time.sleep(sleep_seconds)

if __name__ == "__main__":
    while True:
        if not ASAP:
            # Wait until the scheduled posting time, then generate fresh status text
            wait_until_post_time()
            msg1, msg2, msg3 = generate_status_text()  # This is now called at posting time
            post(msg1, msg2, msg3)
            # Pause briefly after posting (adjust as needed)
            time.sleep(60)
        else:
            # In ASAP mode, generate status text immediately and post
            msg1, msg2, msg3 = generate_status_text()
            post(msg1, msg2, msg3)
            time.sleep(1800)
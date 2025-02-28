from util import *
from secret import API_KEY, BSKY_PASSWORD, BSKY_USERNAME
import time
import pytz
import datetime
from atproto import Client, models, client_utils

client = Client()
client.login(BSKY_USERNAME, BSKY_PASSWORD)

def post(message1: str, message2: str, message3: str, message4: str = None):
    """
    Post a threaded series of messages with an optional fourth message.

    This function posts three mandatory messages in a thread:
      - message1 is posted as the root.
      - message2 is posted as a reply to message1.
      - message3 is posted as a reply to message2.
    If message4 is provided, it is posted as a reply to message3, continuing the thread.

    Parameters:
        message1 (str): The first message to be posted (thread root).
        message2 (str): The second message, posted as a reply to message1.
        message3 (str): The third message, posted as a reply to message2.
        message4 (str, optional): An optional fourth message, posted as a reply to message3.
                                  Defaults to None.

    Raises:
        Exception: Propagates any exception encountered during posting.
    """
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
        
        # Post the third message as a reply to the second post (still part of the same thread)
        response3 = client.send_post(
            message3,
            reply_to=models.AppBskyFeedPost.ReplyRef(
                parent=models.create_strong_ref(response2),
                root=root_ref
            )
        )
        
        # If a fourth message is provided, post it as a reply to the third message
        if message4 is not None:
            response4 = client.send_post(
                message4,
                reply_to=models.AppBskyFeedPost.ReplyRef(
                    parent=models.create_strong_ref(response3),
                    root=root_ref
                )
            )
            success = response4
        else:
            success = response3

        print("Posted successfully!" if success else "Failed to post")
    except Exception as e:
        print(f"Error: {e}")
        raise

ASAP = False  # Set to True to post immediately, for debugging

def wait_until_post_time():
    tz = pytz.timezone("America/Chicago")
    now = datetime.datetime.now(tz)
    # Set target posting time—for example, 9:00 AM CST
    post_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= post_time:
        # If it's already past 8 AM today, wait until tomorrow
        post_time += datetime.timedelta(days=1)
    sleep_seconds = (post_time - now).total_seconds()
    print(f"Sleeping for {sleep_seconds/3600:.2f} hours until 9 AM CST")
    time.sleep(sleep_seconds)

if __name__ == "__main__":
    while True:
        if not ASAP:
            # Wait until the scheduled posting time, then generate fresh status text
            wait_until_post_time()
            msg1, msg2, msg3, msg4 = generate_weekly_report()
            post(msg1, msg2, msg3, msg4)
            # Pause briefly after posting
            time.sleep(60)
        else:
            # In ASAP mode, generate weekly report text immediately and post
            msg1, msg2, msg3, msg4 = generate_weekly_report()
            post(msg1, msg2, msg3, msg4)
            time.sleep(1800)
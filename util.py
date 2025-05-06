import json
import numpy as np
import pandas as pd
import requests
from datetime import datetime, date, time, timedelta
import io
import pytz
from PIL import Image, ImageDraw, ImageFont
import base64
from atproto import Client, models
import time as time_module
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("API_KEY")
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")
BASE_URL = "https://www.uchicagoshuttles.com"

def getApiData(url, key):
    """
    Makes the API request and returns a Pandas DataFrame with
    arrivalTime and departureTime converted into naive US/Central datetimes.
    """
    headers = {
        "key": key,
        "User-Agent": "curl",
    }
    
    response = requests.get(BASE_URL + url, headers=headers)
    if response.status_code != 200:
        raise ValueError(f"ERROR making the API request: {response.text}")
    
    # 1) Read CSV into DataFrame
    df = pd.read_csv(io.StringIO(response.text))
    
    # 2) Parse/convert timestamps
    for col in ["arrivalTime", "departureTime"]:
        df[col] = (
            pd.to_datetime(df[col], utc=True)      # interpret as UTC
              .dt.tz_convert("US/Central")         # shift to Central
              .dt.tz_localize(None)                # drop tzinfo → naive
        )
    
    return df

def utcToCentral(datetime_utc):
    """
    Convert naive UTC datetime objects into naive US/Central datetime objects
    """
    datetime_utc = pytz.utc.localize(datetime_utc)
    datetime_central = datetime_utc.astimezone(pytz.timezone('US/Central'))
    datetime_central = datetime_central.replace(tzinfo=None)
    return datetime_central

def get_headways(data):
    """
    Returns the average headway for each route between the start and end time

    Special thanks to Andrei Thüler for the base calculation, modified by Dariel Cruz Rodriguez 
    """
    
    # Get the stops data
    df_stops = data

    # Compute the Headway
    current_id = df_stops.index[0]
    last_id = df_stops.index[-1]
    lastStop = {}
    lastStopId = {}
    
    # Loop through the stops, calculating headways for each run of a route
    while current_id <= last_id:
        route_stop_id = f"{df_stops.loc[current_id, 'routeId']}-{df_stops.loc[current_id, 'stopId']}"
        route_id = f"{df_stops.loc[current_id, 'routeId']}"
        bus_id = f"{df_stops.loc[current_id, 'busId']}"
        
        if bus_id not in lastStopId.keys():
            lastStopId[bus_id] = None
        
        if (route_stop_id in lastStop.keys()) and (lastStopId[bus_id] != df_stops.loc[current_id, 'stopId']):
            df_stops.loc[current_id, 'headway'] = (df_stops.loc[current_id, 'departureTime'] - lastStop[route_stop_id]).seconds / 60
        else:
            df_stops.loc[current_id, 'headway'] = None
        
        lastStop[route_stop_id] = df_stops.loc[current_id, 'departureTime']
        lastStopId[bus_id] = df_stops.loc[current_id, 'stopId']
        
        current_id += 1
    
    # Drop the NaN values and add a column about whether it is below or above promised headways +- 2 minutes
    df_stops = df_stops.dropna(subset=['headway'])
    df_stops = df_stops[df_stops['headway'] > 0]
    df_stops = df_stops[df_stops['headway'] < 240]  # remove outlying 4 hour layovers, suggested by andrei for overnighters
    
    def get_promised_headway(row):
        route_id = row['routeId']
        route_name = row['routeName']
        
        # Daytime routes
        if route_id == 48618 or route_name == 'Red Line/Arts Block':
            return 20
        elif route_id == 38732 or route_name == '53rd Street Express':
            if row['arrivalTime'].time() >= time(8, 0) and row['arrivalTime'].time() < time(10, 30):
                # if between 8am and 10:30am, 15 minutes
                return 15
            else:
                return 30
        elif route_id == 38729 or route_name == 'Apostolic':
            return 10
        elif route_id == 38730 or route_name == 'Apostolic/Drexel':
            if row['arrivalTime'].time() >= time(15, 0) or row['arrivalTime'].time() < time(0, 30):
                # if between 3pm and 12:30am, 10 minutes
                return 10
            else:
                return 15
        elif route_id == 38728 or route_name == 'Drexel':
            return 10
        elif route_id == 50198 or route_id == 50199 or route_name == 'Downtown Campus Connector':
            return 20
        elif route_id == 38731 or route_id == 38809 or route_name == 'Midway Metra':
            return 10
        elif route_name == 'Friend Center/Metra':
            return 30

        # Nighttime routes
        elif route_id == 38734 or route_name == 'North':
            if row['arrivalTime'].time() >= time(23, 0) or row['arrivalTime'].time() < time(4, 00):
                # between 11pm and 4am, 30 minutes
                return 30
            else:
                return 25
        elif route_id == 38735 or route_name == 'South':
            if row['arrivalTime'].time() >= time(23, 0) or row['arrivalTime'].time() < time(4, 00):
                # between 11pm and 4am, 30 minutes
                return 30
            else:
                return 25
        elif route_id == 38736 or route_name == 'East':
            if row['arrivalTime'].time() >= time(23, 0) or row['arrivalTime'].time() < time(4, 00):
                # between 11pm and 4am, 30 minutes
                return 30
            else:
                return 25
        elif route_id == 38737 or route_name == 'Central':
            if row['arrivalTime'].time() >= time(23, 0) or row['arrivalTime'].time() < time(4, 00):
                # between 11pm and 4am, 30 minutes
                return 30
            else:
                return 25
        elif route_id == 40515 or route_name == 'Regents Express':
            return 30
        elif route_name == 'South Loop Shuttle':
            return 60
        else:
            return np.nan


    # Records whether that specific run met the promised headway
    df_stops["promised_headway"] = df_stops.apply(get_promised_headway, axis=1)

    def check_headway(row):
        night_route = {"North", "South", "East", "Central"}
        night_route_id = {38734, 38735, 38736, 38737}

        # No promised headway → can’t judge
        if pd.isnull(row["promised_headway"]):
            return False

        t = row["headway"]

        # Special night‐route window (still ±range around 15–25)
        #if row["routeName"] in night_route or row["routeId"] in night_route_id:
        #   return 10 <= t <= 30

        # Special Red Line/Arts Block window
        #if row["routeName"] == "Red Line/Arts Block" or row["routeId"] == 48618:
        #    return 5 <= t <= 25

        # For everything else: only fail if you’re more than 5 min _late_.
        # i.e. allow any early headways, and anything up to (promised + 5).
        return t <= row["promised_headway"] + 5

    df_stops["meetPromisedHeadway"] = df_stops.apply(check_headway, axis=1)
    
    # Other data cleaning (dropping irrelevant columns)
    df_stops = df_stops.drop(columns=["id","stopDurationSeconds", "arrivalTime", "departureTime","nextStopId"])
    df_stops = df_stops.dropna(subset=["promised_headway"])

    return df_stops

def route_performance(data):
    """
    Calculate route performance by evaluating how well each route adheres to its promised headway.
    """
    headways = get_headways(data)
    aggregated = headways.groupby(['routeName','routeId'])['meetPromisedHeadway'].agg(total_true='sum', total_count='count').reset_index()
    aggregated['total_false'] = aggregated['total_count'] - aggregated['total_true']
    aggregated['total'] = aggregated['total_true'] + aggregated['total_false']
    return aggregated[['routeName', 'routeId', 'total_true', 'total_false', 'total']]

def get_ridership(data):
    ridership = get_headways(data) 
    return ridership['passengerLoad'].sum()

def make_photo(data, img_type="neutral"):
    """
    Takes in the same data thats going into the caption and returns the image to be used in IG post.
    """
    output_image_path = "images/generated_image.jpg"
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")
    riders = get_ridership(data)

    if img_type in ["neutral", "good", "bad"]:
        base_image_path = f"images/{img_type}template.png"
    else:
        base_image_path = f"images/neutraltemplate.png"

    image = Image.open(base_image_path)
    draw = ImageDraw.Draw(image)

    font_path = "fonts/Gotham-Medium.otf" 
    font_size = 200
    font = ImageFont.truetype(font_path, font_size)
    rider_font = ImageFont.truetype(font_path, 130)
    date_font = ImageFont.truetype(font_path, 65)
    text_color = (255, 255, 255)

    data_metrics = {
        "date": str(date_str),
        "ridership": str(riders),
        "averageheadway": f"{int(((route_performance(data)['total_true'].sum())/(route_performance(data)['total'].sum()))*100)}%"
    }

    # to center the date
    img_width, img_height = image.size
    date_text = data_metrics["date"]
    text_bbox = date_font.getbbox(date_text)
    text_width = text_bbox[2] - text_bbox[0]
    centered_x = (img_width - text_width) // 2
    date_position = (centered_x, 466.3)

    # to center the ridership
    img_width, img_height = image.size
    rider_text = data_metrics["ridership"]
    text_bbox = rider_font.getbbox(rider_text)
    text_width = text_bbox[2] - text_bbox[0]
    rider_centered_x = (img_width - text_width) // 2

    # to center the ontime percentage
    img_width, img_height = image.size
    avgheadway_text = data_metrics["averageheadway"]
    text_bbox = font.getbbox(avgheadway_text)
    text_width = text_bbox[2] - text_bbox[0]
    avg_headway_x = (img_width - text_width) // 2

    text_positions = {
        "date": date_position,  # (x, y)
        "ridership": (rider_centered_x, 885),
        "averageheadway": (avg_headway_x, 550)
    }

    for key, text in data_metrics.items():
        position = text_positions[key]
        if key == "date":
            draw.text(position, text, fill=text_color, font=date_font, align="center")
        elif key == "ridership":
            draw.text(position, text, fill=text_color, font=rider_font, align="center")
        else:
            draw.text(position, text, fill=text_color, font=font, align="center")

    # save image locally
    image = image.convert("RGB")
    image.save(output_image_path)
    print(f"Image saved as {output_image_path}")

    # upload image online
    url = "https://api.imgur.com/3/image"
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}

    with open(output_image_path, "rb") as file:
        data = file.read()
        base64_data = base64.b64encode(data)

    response = requests.post(url, headers=headers, data={"image": base64_data})
    imgurl = response.json()["data"]["link"]
    print(f"Image uploaded at {imgurl}")

    return imgurl

def get_caption(data, platform="BSKY"):

    # Calculate the busiest stop based on passengerLoad
    stop_loads = data.groupby('stopName')['passengerLoad'].sum()
    busiest_stop = stop_loads.idxmax()
    busiest_stop_load = stop_loads.max()
    headways = get_headways(data)
    performance = route_performance(data)
    ridership = get_ridership(data)

    benchmark = 0.80

    overall_rate = performance['total_true'].sum() / performance['total'].sum()
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")
    
    # Message 1 contents
    numberofruns = headways.shape[0]
    ontimeruns = performance['total_true'].sum()
    worst_route = performance.loc[(performance['total_true']/performance['total']).idxmin()]["routeName"]
    best_route = performance.loc[(performance['total_true'] / performance['total']).idxmax()]["routeName"]
    delay_modifier = "had troubles running" if overall_rate < 0.8 else "ran smoothly"
    
    if platform=="IG":
        message = f"""UGo shuttle services {delay_modifier} yesterday on {date_str}. Out of {numberofruns} runs, {ontimeruns} were on time.

    👎 The worst route was {worst_route}, where {((performance['total_true']/performance['total']).min()*100):.2f}% of runs had acceptable headways.
    👍 The best route was {best_route}, which had an on-time performance of {((performance['total_true']/performance['total']).max()*100):.2f}%.

    🧍‍♂️ {ridership} Maroons rode the shuttles, and the busiest stop was {busiest_stop} with {busiest_stop_load} tap-ins.
    """
        return message

    if platform=="BSKY":
        message1 = f"UGo shuttle services {delay_modifier} yesterday on {date_str}. Out of {numberofruns} runs, {ontimeruns} were on time."
        message2 = f"👎 The worst route was {worst_route}, where only {((performance['total_true']/performance['total']).min()*100):.2f}% of the runs had acceptable headways.\n👍 The best route was {best_route}, which had an on-time performance of {((performance['total_true']/performance['total']).max()*100):.2f}%."
        message3 = f"🧍‍♂️ {ridership} Maroons rode the shuttles, and the busiest stop was {busiest_stop} with {busiest_stop_load} tap-ins."
        return message1, message2, message3

def post(caption, platform=None, image=None):
    if platform is None:
        return ValueError("No platform specified!")
    
    BSKY_USERNAME = "bsky.uchicagoshuttles.com"
    BSKY_PASSWORD = os.getenv("BSKY_PASSWORD")
    safecaption = caption[:300]

    if platform=="BSKY":
        client = Client()
        client.login(BSKY_USERNAME, BSKY_PASSWORD)

        message1, message2, message3 = caption

        if image is not None:
            with open('images/generated_image.jpg', 'rb') as f:
                img_data = f.read()

                response1 = client.send_image(text=message1, image=img_data, image_alt='Status image')
                root_ref = models.create_strong_ref(response1)
                print("Posted thread 1/3 with image!")

                response2 = client.send_post(message2,
                    reply_to=models.AppBskyFeedPost.ReplyRef(
                        parent=models.create_strong_ref(response1),
                        root=root_ref))
                print("Posted thread 2/3!")

                response2 = client.send_post(message3,
                    reply_to=models.AppBskyFeedPost.ReplyRef(
                        parent=models.create_strong_ref(response2),
                        root=root_ref))
                print("Posted thread 3/3!")

        if image is None:
            client.send_post(caption)
            print("Posted without image")
        
    if platform=="IG":
        INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
        ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
        INSTAGRAM_GRAPH_API = "https://graph.instagram.com/v22.0"

        url = f"{INSTAGRAM_GRAPH_API}/{INSTAGRAM_ACCOUNT_ID}/media"
        payload = {
            "caption": caption,
            "access_token": ACCESS_TOKEN,
            "media_type": "IMAGE",
            "image_url": image
        }

        response = requests.post(url, data=payload)

        if response.status_code == 200:
            media_id = response.json().get("id")
            print(f"Image uploaded successfully! Media ID: {media_id}")

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

def bad_or_good(data):
    performance = route_performance(data)
    benchmark = 0.80
    overall_rate = performance['total_true'].sum() / performance['total'].sum()
    status = "bad" if overall_rate < benchmark else "good"
    return status

def wait_until_post_time(desiredtime="8:00"):
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz)
    
    hour = int(desiredtime.split(":")[0])
    minute = int(desiredtime.split(":")[1])
    
    post_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= post_time:
        # If it's already past 8 AM today, wait until tomorrow
        post_time += timedelta(days=1)
    sleep_seconds = (post_time - now).total_seconds()
    print(f"Sleeping for {sleep_seconds/3600:.2f} hours until {desiredtime} CST")
    time_module.sleep(sleep_seconds)

def runbot(platform="BSKY"):
    # Determine yesterday's date in US/Central time
    central_tz = pytz.timezone('US/Central')
    now_central = datetime.now(central_tz)
    yesterday_date = now_central.date() - timedelta(days=1)

    # Create naive datetime objects for the start and end of yesterday in US/Central time
    start_central_naive = datetime.combine(yesterday_date, time(0, 0, 0))
    end_central_naive   = datetime.combine(yesterday_date, time(23, 59, 59))

    # Localize these naive times to US/Central to get timezone-aware objects
    start_central = central_tz.localize(start_central_naive)
    end_central   = central_tz.localize(end_central_naive)

    # Convert the US/Central times to UTC for use in UTC-based filtering
    start_utc = start_central.astimezone(pytz.utc)
    end_utc   = end_central.astimezone(pytz.utc)

    # Format the UTC datetimes as strings if needed
    start = start_utc.strftime("%Y-%m-%d %H:%M:%S")
    end = end_utc.strftime("%Y-%m-%d %H:%M:%S")

    url = f"/api/getStops?start={start}&end={end}"
    data = getApiData(url, API_KEY)

    caption = get_caption(data=data, platform=platform)
    status = bad_or_good(data)
    img = make_photo(data=data, img_type=status)

    post(caption, platform=platform, image=img)
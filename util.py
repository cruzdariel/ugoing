import datetime
import json
import numpy as np
import pandas as pd
import requests
from datetime import datetime, date, time, timedelta
import io
import pytz
from PIL import Image, ImageDraw, ImageFont
#import passiogo  https://github.com/athuler/PassioGo

from secret import API_KEY

BASE_URL = "https://uchicagoshuttles.com"

def getApiData(url, key):
    """
    Makes the API request and returns a Pandas dataframe
    """
    headers = {
        "key":API_KEY,
        "User-Agent": "curl",
    }
    
    response = requests.request("GET", BASE_URL+url, headers=headers)
    if response.status_code == 200:
        return(pd.read_csv(io.StringIO(response.text)))
    else:
        raise ValueError(f"ERROR making the API request: {response.text}")

def utcToCentral(datetime_utc):
    """
    Convert naive UTC datetime objects into naive US/Central datetime objects
    """
    datetime_utc = pytz.utc.localize(datetime_utc)
    datetime_central = datetime_utc.astimezone(pytz.timezone('US/Central'))
    datetime_central = datetime_central.replace(tzinfo=None)
    return datetime_central

    
def avg_headway(start=None, end=None):
    """
    Returns the average headway for each route between the start and end time

    Special thanks to Andrei Thüler for the base calculation, modified by Dariel Cruz Rodriguez 
    """
    if start is None or end is None:
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

    print(f"Headway data is pulled between {start} and {end}")

    # Get the stops data
    url = f"/api/getStops?start={start}&end={end}"
    df_stops = getApiData(url, API_KEY)

    # Convert the times to datetime objects
    df_stops["arrivalTime"] = pd.to_datetime(df_stops["arrivalTime"])
    df_stops["departureTime"] = pd.to_datetime(df_stops["departureTime"])

    # Convert the times to US/Central
    df_stops["arrivalTime"] = df_stops["arrivalTime"].apply(lambda x: utcToCentral(x))
    df_stops["departureTime"] = df_stops["departureTime"].apply(lambda x: utcToCentral(x))
    
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
    
    # Drop the NaN values, and group average headways by route
    df_stops = df_stops.dropna(subset=['headway'])
    df_stops = df_stops[df_stops['headway'] > 0]
    df_stops = df_stops[df_stops['headway'] < 240]  # remove outlying 4 hour layovers, suggested by andrei for overnighters
    avg_headways = df_stops.groupby(['routeName','routeId'])['headway'].mean().reset_index()
    return avg_headways

def route_averages(timetype='day'):
    """
    Returns the difference between average headway and guaranteed headway for each route, based
    on it's pull off stop. For routes with multiple guaranteed headways throughout the day, the
    longest headway is used
    """
    if timetype == 'day':
        avg_headways = avg_headway()
    elif timetype == 'week':
        central_tz = pytz.timezone('US/Central')

        # Get the current time in US/Central
        now_central = datetime.now(central_tz)

        # For the end time: use yesterday at 11:59 PM in US/Central
        yesterday_date = now_central.date() - timedelta(days=1)
        # Note: 11:59 PM is 23:59 in 24-hour time.
        end_central_naive = datetime.combine(yesterday_date, time(23, 59, 0))
        end_central = central_tz.localize(end_central_naive)
        end_utc = end_central.astimezone(pytz.utc)
        endtime = end_utc.strftime("%Y-%m-%d %H:%M:%S")

        # For the start time: 7 days ago (from now) at 00:00:00 in US/Central
        start_date = (now_central - timedelta(days=7)).date()
        start_central_naive = datetime.combine(start_date, time(0, 0, 0))
        start_central = central_tz.localize(start_central_naive)
        start_utc = start_central.astimezone(pytz.utc)
        starttime = start_utc.strftime("%Y-%m-%d %H:%M:%S")

        avg_headways = avg_headway(start=starttime, end=endtime)

    # Daytime routes
    daytime_routes = [48618, 38601, 38728, 38729, 38730, 38731, 38809, 38732, 50198, 50199]
    daytime_routes_names = ['Red Line/Arts Block', '53rd Street Express', 'Apostolic', 'Apostolic/Drexel', 
                            'Drexel', 'Downtown Campus Connector', 'Midway Metra'] # this is not used, but a redundancy
    daytime_hw = avg_headways[avg_headways['routeId'].isin(daytime_routes)]
    daytime_score = {}

    for _, row in daytime_hw.iterrows():
        route_id = row['routeId']
        route_name = row['routeName']
        headway = row['headway']
    
        # Check both route ID and route name
        if route_id == 48618 or route_name == 'Red Line/Arts Block':
            daytime_score[route_name] = headway - 20
        elif route_id == 38732 or route_name == '53rd Street Express':
            daytime_score[route_name] = headway - 30
        elif route_id == 38729 or route_name == 'Apostolic':
            daytime_score[route_name] = headway - 30
        elif route_id == 38730 or route_name == 'Apostolic/Drexel':
            daytime_score[route_name] = headway - 15
        elif route_id == 38728 or route_name == 'Drexel':
            daytime_score[route_name] = headway - 10
        elif route_id == 50198 or route_id == 50199 or route_name == 'Downtown Campus Connector':
            daytime_score[route_name] = headway - 20
        elif route_id == 38731 or route_id == 38809 or route_name == 'Midway Metra':
            daytime_score[route_name] = headway - 30
        else:
            pass

    # Nighttime routes
    nighttime_routes = [38734, 38735, 38736, 38737, 40515]
    nighttime_routes_names = ['North', 'South', 'East', 'Central', 'Regents Express', 'South Loop Shuttle']
    nighttime_hw = avg_headways[avg_headways['routeId'].isin(nighttime_routes) | 
                              avg_headways['routeName'].isin(nighttime_routes_names)]
    nightime_score = {}

    for _, row in nighttime_hw.iterrows():
        route_id = row['routeId']
        route_name = row['routeName']
        headway = row['headway']
        
        # Check both route ID and route name
        if route_id == 38734 or route_name == 'North':
            nightime_score[route_name] = headway - 30
        elif route_id == 38735 or route_name == 'South':
            nightime_score[route_name] = headway - 30
        elif route_id == 38736 or route_name == 'East':
            nightime_score[route_name] = headway - 30
        elif route_id == 38737 or route_name == 'Central':
            nightime_score[route_name] = headway - 30
        elif route_id == 40515 or route_name == 'Regents Express':
            nightime_score[route_name] = headway - 30
        elif route_name == 'South Loop Shuttle':
            nightime_score[route_name] = headway - 60
        else:
            pass

    return nightime_score, daytime_score

def call_them_out(timetype='day'):
    if timetype == 'day':
        nighttime_scores, daytime_scores = route_averages()
    elif timetype == 'week':
        nighttime_scores, daytime_scores = route_averages(timetype='week')

    total_daytime = 0
    total_nighttime = 0
    ontime_daytime = 0
    ontime_nighttime = 0
    delayed_daytime = 0
    delayed_nighttime = 0
    delayed_daytime_routes = []
    delayed_nighttime_routes = []
    delaynums = []
    delaynums_daytime = []
    delaynums_nighttime = []

    if nighttime_scores == {}:
        print('All routes are on time')
    else:
        for route_name, delay in nighttime_scores.items():
            total_nighttime += 1
            delaynums.append(delay)
            if delay > 0:
                #print(f"{route_name} ran {int(delay)} minutes behind schedule on average")
                delayed_nighttime += 1
                delayed_nighttime_routes.append(route_name)
                delaynums_nighttime.append(delay)
            elif delay == 0:
                #print(f"{route_name} ran on time")
                ontime_nighttime += 1
            elif delay < 0: 
                #print(f"{route_name} ran {abs(int(delay))} minutes ahead of schedule on average")
                ontime_nighttime += 1
    
    if daytime_scores == {}:
        print('All routes are on time')
    else:
        for route_name, delay in daytime_scores.items():
            total_daytime +=1
            delaynums.append(delay)
            if delay > 0:
                #print(f"{route_name} ran {int(delay)} minutes behind schedule on average")
                delayed_daytime += 1
                delayed_daytime_routes.append(route_name)
                delaynums_daytime.append(delay)
            elif delay == 0:
                #print(f"{route_name} ran on time")
                ontime_daytime += 1
            elif delay < 0: 
                #print(f"{route_name} ran {abs(int(delay))} minutes ahead of schedule on average")
                ontime_daytime += 1
    
    daytime_ratio = ontime_daytime / total_daytime if total_daytime else 0
    nighttime_ratio = ontime_nighttime / total_nighttime if total_daytime else 0
    total_ratio = (ontime_daytime + ontime_nighttime) / (total_daytime + total_nighttime)
    average_delay = np.mean(delaynums) if len(delaynums) > 0 else 0
    average_delay_daytime = np.mean(delaynums_daytime) if len(delaynums_daytime) > 0 else 0
    average_delay_nighttime = np.mean(delaynums_nighttime) if len(delaynums_nighttime) > 0 else 0

    return daytime_ratio, nighttime_ratio, delayed_daytime_routes, delayed_nighttime_routes, average_delay, average_delay_daytime, average_delay_nighttime, total_ratio

#print(call_them_out())

def get_passengers(timetype='week'):
    if timetype=='week':
        # Define the US/Central timezone
        central_tz = pytz.timezone('US/Central')

        # Get the current time in US/Central
        now_central = datetime.now(central_tz)

        # For the end time: use yesterday at 11:59 PM in US/Central
        yesterday_date = now_central.date() - timedelta(days=1)
        # Note: 11:59 PM is 23:59 in 24-hour time.
        end_central_naive = datetime.combine(yesterday_date, time(23, 59, 0))
        end_central = central_tz.localize(end_central_naive)
        end_utc = end_central.astimezone(pytz.utc)
        endtime = end_utc.strftime("%Y-%m-%d %H:%M:%S")

        # For the start time: 7 days ago (from now) at 00:00:00 in US/Central
        start_date = (now_central - timedelta(days=7)).date()
        start_central_naive = datetime.combine(start_date, time(0, 0, 0))
        start_central = central_tz.localize(start_central_naive)
        start_utc = start_central.astimezone(pytz.utc)
        starttime = start_utc.strftime("%Y-%m-%d %H:%M:%S")

        print(f"Ridership data start time: {starttime}, End time: {endtime}")

        url = f"/api/getRidership?start={starttime}&end={endtime}&aggregate=day"
        df_total_ridership = getApiData(url, API_KEY)

        dailyridership = {}
        for day, ridership in zip(df_total_ridership['timeReported'], df_total_ridership['ridership']):
            day = datetime.strptime(day, "%Y-%m-%d %H:%M").strftime("%A")
            dailyridership[day] = ridership

        total_ridership = np.sum(df_total_ridership['ridership'])
        day_mostridership = max(dailyridership, key=dailyridership.get)
        day_mostridershipval = max(dailyridership.values())
        day_leastridership = min(dailyridership, key=dailyridership.get)
        day_leastridershipval = min(dailyridership.values())

        return dailyridership, total_ridership, day_mostridership, day_mostridershipval, day_leastridership, day_leastridershipval
    elif timetype=='day':
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
        starttime = start_utc.strftime("%Y-%m-%d %H:%M:%S")
        endtime = end_utc.strftime("%Y-%m-%d %H:%M:%S")
        print(f"Ridership data start time: {starttime}, End time: {endtime}")

        url = f"/api/getRidership?start={starttime}&end={endtime}&aggregate=hour"
        df_total_ridership = getApiData(url, API_KEY)
        total_ridership = np.sum(df_total_ridership['ridership'])
        hour_mostridershipraw = df_total_ridership.loc[df_total_ridership['ridership'].idxmax()]['timeReported']
        hour_mostridership = pytz.utc.localize(datetime.strptime(hour_mostridershipraw, "%Y-%m-%d %H:%M")).astimezone(pytz.timezone("America/Chicago")).strftime("%I %p").lstrip("0")
        hour_mostridershipval = df_total_ridership['ridership'].max()
        return df_total_ridership, total_ridership, hour_mostridership, hour_mostridershipval

def generate_weekly_report():
    """
    Generates a status message using data from call_them_out() for the entire week.
    """
    # Retrieve metrics from call_them_out()
    (daytime_ratio, nighttime_ratio,
     delayed_daytime_routes, delayed_nighttime_routes,
     average_delay, average_delay_daytime, average_delay_nighttime, total_ratio) = call_them_out(timetype='week')
    
    (dailyridership, total_ridership, day_mostridership, day_mostridershipval, 
    day_leastridership, day_leastridershipval) = get_passengers(timetype='week')

    # Use yesterday's date for the output
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")
    
    # Determine modifier for the UGoing? sentence: "not" if overall delay is positive
    delay_modifier = "bad" if average_delay > 5 else "good"
    
    # Create overall delay description text
    if average_delay > 5:
        overall_delay_text = f"{round(average_delay, 1)} minutes behind guaranteed headways, if they weren't on the {int(total_ratio*100)}% of on-time shuttles"
    elif average_delay < 0:
        overall_delay_text = f"{round(abs(average_delay), 1)} minutes ahead of guaranteed headways, if they were on the {int(total_ratio*100)}% of on-time shuttles"
    else:
        overall_delay_text = f"roughly on par with guaranteed headways, {int(total_ratio*100)}% of shuttles were on-time time."
    
    # Begin constructing the message
    message1 = (
        f"🎉 Happy Friday! UGo had a {delay_modifier} week moving Maroons around. (week ending: {date_str}). "
        f"This week students could expect to wait {overall_delay_text}.\n\nLearn more in the thread ⬇️"
    )

    message2 = ""
    message3 = ""
    
    # Format daytime information
    daytime_pct = f"{round(daytime_ratio * 100, 1)}%"
    message2 += f"☀️ This week, {daytime_pct} of daytime routes ran on time."
    if delayed_daytime_routes and (average_delay_daytime is not None):
        routes_str = ", ".join(delayed_daytime_routes)
        message2 += f" The {routes_str} routes suffered delays averaging {round(average_delay_daytime, 1)} minutes."
    #message2 += "\n"
    
    # Format nighttime information
    nighttime_pct = f"{round(nighttime_ratio * 100, 1)}%"
    message3 += f"🌙 This week, {nighttime_pct} of nighttime routes ran on time."
    if delayed_nighttime_routes and (average_delay_nighttime is not None):
        routes_str = ", ".join(delayed_nighttime_routes)
        message3 += f" The {routes_str} routes suffered delays averaging {round(average_delay_nighttime, 1)} minutes."
    
    message4 = f"👫 This week, there were {total_ridership} tap-ins on UGo, averaging to about {int(total_ridership/7)} riders/day.\n\nThe busiest day was on {day_mostridership if day_mostridership != 'Friday' else f'last {day_mostridership}'} with {day_mostridershipval} riders.\nThe quietest day was {day_leastridership if day_mostridership != 'Friday' else f'last {day_leastridership}'} with {day_leastridershipval} riders."
    
    return message1, message2, message3, message4


def generate_status_text():
    """
    Generates a status message using data from call_them_out().
    """
    # Retrieve metrics from call_them_out()
    (daytime_ratio, nighttime_ratio,
     delayed_daytime_routes, delayed_nighttime_routes,
     average_delay, average_delay_daytime, average_delay_nighttime, total_ratio) = call_them_out()
    
    (df_total_ridership, total_ridership, hour_mostridership, 
    hour_mostridershipval) = get_passengers(timetype='day')

    # Use yesterday's date for the output
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")
    
    # Determine modifier for the UGoing? sentence: "not" if overall delay is positive
    delay_modifier = "probably didn't" if average_delay > 0 else "probably did"
    
    # Create overall delay description text
    if average_delay > 0:
        overall_delay_text = f"{round(average_delay, 1)} minutes longer than the guaranteed headways."
    elif average_delay < 0:
        overall_delay_text = f"{round(abs(average_delay), 1)} minutes less than the guaranteed headways."
    else:
        overall_delay_text = "to the guaranteed headways"
    
    # Begin constructing the message
    message1 = (
        f"UGOing? {total_ridership} riders {delay_modifier} yesterday, {date_str}.\n\n"
        f"UGo Shuttles overall ran on average {overall_delay_text}. Their busiest hour was {hour_mostridership} with {hour_mostridershipval} tap-ins.\n\nLearn more ⬇️"
    )

    message2 = ""
    message3 = ""
    
    # Format daytime information
    if daytime_ratio == 0:
        message2 = f"Daytime routes did not run yesterday, {date_str}. Daytime shuttle routes run Monday through Friday"
    else:
        daytime_pct = f"{round(daytime_ratio * 100, 1)}%"
        message2 = f"☀️ During the day, {daytime_pct} of daytime routes ran on time."
        if delayed_daytime_routes and (average_delay_daytime is not None):
            routes_str = ", ".join(delayed_daytime_routes)
            message2 += f" The {routes_str} routes suffered delays averaging {round(average_delay_daytime, 1)} minutes."
    
    # Format nighttime information
    nighttime_pct = f"{round(nighttime_ratio * 100, 1)}%"
    message3 += f"🌙 During the night, {nighttime_pct} of nighttime routes ran on time."
    if delayed_nighttime_routes and (average_delay_nighttime is not None):
        routes_str = ", ".join(delayed_nighttime_routes)
        message3 += f" The {routes_str} routes suffered delays averaging {round(average_delay_nighttime, 1)} minutes."
    
    return message1, message2, message3

def make_photo(img_type="good"):
    """
    Takes in the same data thats going into the caption and returns the image to be used in IG post.
    """
    (daytime_ratio, nighttime_ratio,
    delayed_daytime_routes, delayed_nighttime_routes,
    average_delay, average_delay_daytime, average_delay_nighttime, total_ratio) = call_them_out()
    
    (df_total_ridership, total_ridership, hour_mostridership, 
    hour_mostridershipval) = get_passengers(timetype='day')

    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")

    def get_left_aligned_x(anchor_x, text, font):
        """ Adjusts text position so it expands leftward from the anchor point. """
        text_bbox = font.getbbox(text)
        text_width = text_bbox[2] - text_bbox[0]  # Get text width
        return anchor_x - text_width  # Shift left completely

    if img_type == "good":
        base_image_path = "images/goodtemplate.png"
        output_image_path = "images/generated_image.jpg"

        image = Image.open(base_image_path)
        draw = ImageDraw.Draw(image)

        font_path = "fonts/Gotham-Medium.otf" 
        font_size = 55
        font = ImageFont.truetype(font_path, font_size)
        date_font = ImageFont.truetype(font_path, 65)
        text_color = (255, 255, 255)

        data_metrics = {
            "date": str(date_str),
            "ridership": str(total_ridership),
            "averageheadway": str(int(abs(average_delay)))
        }

        # to center the date
        img_width, img_height = image.size
        date_text = data_metrics["date"]
        text_bbox = date_font.getbbox(date_text)
        text_width = text_bbox[2] - text_bbox[0]
        centered_x = (img_width - text_width) // 2
        date_position = (centered_x, 526.3)

        orig_text_positions = {
            "date": date_position,  # (x, y)
            "ridership": (238, 715),
            "averageheadway": (320, 787)
        }

        ridership_x = get_left_aligned_x(orig_text_positions["ridership"][0], data_metrics["ridership"], font)
        avg_headway_x = get_left_aligned_x(orig_text_positions["averageheadway"][0], data_metrics["averageheadway"], font)

        text_positions = {
            "date": date_position,  # (x, y)
            "ridership": (ridership_x, 715),
            "averageheadway": (avg_headway_x, 787)
        }

        for key, text in data_metrics.items():
            position = text_positions[key]
            if key == "date":
                draw.text(position, text, fill=text_color, font=date_font, align="center")
            else:
                draw.text(position, text, fill=text_color, font=font, align="center")
    elif img_type == "bad":
            base_image_path = "images/badtemplate.png"
            output_image_path = "images/generated_image.jpg"

            image = Image.open(base_image_path)
            draw = ImageDraw.Draw(image)

            font_path = "fonts/Gotham-Medium.otf" 
            font_size = 55
            font = ImageFont.truetype(font_path, font_size)
            date_font = ImageFont.truetype(font_path, 65)
            text_color = (255, 255, 255)

            data_metrics = {
                "date": str(date_str),
                "ridership": str(total_ridership),
                "averageheadway": str(int(abs(average_delay)))
            }

            # to center the date
            img_width, img_height = image.size
            date_text = data_metrics["date"]
            text_bbox = date_font.getbbox(date_text)
            text_width = text_bbox[2] - text_bbox[0]
            centered_x = (img_width - text_width) // 2
            date_position = (centered_x, 526.3)

            orig_text_positions = {
                "date": date_position,  # (x, y)
                "ridership": (248, 715),
                "averageheadway": (310, 787)
            }

            ridership_x = get_left_aligned_x(orig_text_positions["ridership"][0], data_metrics["ridership"], font)
            avg_headway_x = get_left_aligned_x(orig_text_positions["averageheadway"][0], data_metrics["averageheadway"], font)

            text_positions = {
                "date": date_position,  # (x, y)
                "ridership": (ridership_x, 715),
                "averageheadway": (avg_headway_x, 787)
            }

            for key, text in data_metrics.items():
                position = text_positions[key]
                if key == "date":
                    draw.text(position, text, fill=text_color, font=date_font, align="center")
                else:
                    draw.text(position, text, fill=text_color, font=font, align="center")
    image = image.convert("RGB")
    image.save(output_image_path)
    print(f"Image saved as {output_image_path}")

#print(generate_status_text())

import datetime
import json
import numpy as np
import pandas as pd
import requests
from datetime import datetime, date, time, timedelta
import io
import pytz
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

    print(f"Data is pulled between {start} and {end}")

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

def route_averages():
    """
    Returns the difference between average headway and guaranteed headway for each route, based
    on it's pull off stop. For routes with multiple guaranteed headways throughout the day, the
    longest headway is used
    """
    avg_headways = avg_headway()
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
            daytime_score[route_name] = headway - 30
        elif route_id == 38732 or route_name == '53rd Street Express':
            daytime_score[route_name] = headway - 30
        elif route_id == 38729 or route_name == 'Apostolic':
            daytime_score[route_name] = headway - 30
        elif route_id == 38730 or route_name == 'Apostolic/Drexel':
            daytime_score[route_name] = headway - 30
        elif route_id == 38728 or route_name == 'Dresel':
            daytime_score[route_name] = headway - 30
        elif route_id == 50198 or route_id == 50199 or route_name == 'Downtown Campus Connector':
            daytime_score[route_name] = headway - 30
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
            nightime_score[route_name] = headway - 30
        else:
            pass

    return nightime_score, daytime_score

def call_them_out():
    nighttime_scores, daytime_scores = route_averages()

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
    
    daytime_ratio = ontime_daytime / total_daytime
    nighttime_ratio = ontime_nighttime / total_nighttime
    average_delay = np.mean(delaynums)
    average_delay_daytime = np.mean(delaynums_daytime)
    average_delay_nighttime = np.mean(delaynums_nighttime)

    return daytime_ratio, nighttime_ratio, delayed_daytime_routes, delayed_nighttime_routes, average_delay, average_delay_daytime, average_delay_nighttime

#print(call_them_out())

def generate_status_text():
    """
    Generates a status message using data from call_them_out().
    """
    from datetime import datetime, timedelta

    # Retrieve metrics from call_them_out()
    (daytime_ratio, nighttime_ratio,
     delayed_daytime_routes, delayed_nighttime_routes,
     average_delay, average_delay_daytime, average_delay_nighttime) = call_them_out()
    
    # Use yesterday's date for the output
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d, %Y")
    
    # Determine modifier for the UGoing? sentence: "not" if overall delay is positive
    delay_modifier = "Probably not" if average_delay > 0 else "Probably did"
    
    # Create overall delay description text
    if average_delay > 0:
        overall_delay_text = f"{round(average_delay, 1)} minutes behind schedule"
    elif average_delay < 0:
        overall_delay_text = f"{round(abs(average_delay), 1)} minutes ahead of schedule"
    else:
        overall_delay_text = "on schedule"
    
    # Begin constructing the message
    message1 = (
        f"UGoing? {delay_modifier} yesterday ({date_str}). "
        f"UGo Shuttles overall ran on average {overall_delay_text}."
    )

    message2 = ""
    message3 = ""
    
    # Format daytime information
    daytime_pct = f"{round(daytime_ratio * 100, 1)}%"
    message2 += f"☀️ During the day, {daytime_pct} of daytime routes ran on time."
    if delayed_daytime_routes and (average_delay_daytime is not None):
        routes_str = ", ".join(delayed_daytime_routes)
        message2 += f" The {routes_str} routes suffered delays averaging {round(average_delay_daytime, 1)} minutes."
    #message2 += "\n"
    
    # Format nighttime information
    nighttime_pct = f"{round(nighttime_ratio * 100, 1)}%"
    message3 += f"🌙 During the night, {nighttime_pct} of nighttime routes ran on time."
    if delayed_nighttime_routes and (average_delay_nighttime is not None):
        routes_str = ", ".join(delayed_nighttime_routes)
        message3 += f" The {routes_str} routes suffered delays averaging {round(average_delay_nighttime, 1)} minutes."
    
    return message1, message2, message3

#print(generate_status_text())

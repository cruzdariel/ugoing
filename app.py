from util import *
import time as time_module

ASAP = False
ASAPplatform = None

if __name__ == "__main__":
    while True:
        if not ASAP:
            # Wait until the scheduled posting time, then generate fresh status text
            wait_until_post_time()
            
            runbot(platform="IG")
            runbot(platform="BSKY")
            time_module.sleep(60)
        else:
            if ASAPplatform is None:
                runbot(platform="IG")
                runbot(platform="BSKY")
            if ASAPplatform is not None:
                runbot(platform=ASAPplatform)
            time_module.sleep(1800)
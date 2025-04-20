# https://projects.raspberrypi.org/en/projects/get-started-pico-w/2 
import network
from time import sleep
import time
from machine import Pin 

from STEM_Embassy import TSEwebsocket

print("* Starting up ")

# VARS ------------------------------------------------------

#Internet
ssid = 'KML-17-19'
password = 'driefelja32'

#WebSocket
wsHost = "192.168.200.247"
wsPort = 8080
ws = TSEwebsocket.WebSocketClient(wsHost,wsPort)

pin = Pin("LED", Pin.OUT)


# GENERAL FUNCS ----------------------------------------------
def cleanup():
    print("Stopping and resetting everything")
    pin.off()


def blink():
    pin.toggle()
    sleep(0.5)
    pin.toggle()

# WIFI FUNCS --------------------------------------------------
def connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    print('* Waiting for WiFi connection...')
    
    # Adding a 30-second timeout for WiFi connection
    max_wait = 30
    while max_wait > 0:
        if wlan.isconnected():
            break
        max_wait -= 1
        print(".", end="")
        sleep(1)
    
    if wlan.isconnected():
        print("\n* Wifi Connected!")
        print(f"* IP Address: {wlan.ifconfig()[0]}")
        return True
    else:
        print("\n* WiFi connection failed!")
        return False

# SETUP  -----------------------------------------------------------
try:
    if not connect():
        print("* WiFi setup failed")
        cleanup()
        
    if not ws.connect():
        print("* WebSocket setup failed")
        cleanup()

    print("* Setup complete, entering main loop")


    # MAIN LOOP -----------------------------------------------------------    
    while True:
        # Process WebSocket communications
        message = ws.receive_message()

        print(f"Received message: {message}")

except KeyboardInterrupt:
    print("* Connection stopped by user")
except Exception as e:
    print(f"* Unexpected error: {e}")
finally:
    cleanup()
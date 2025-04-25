# https://projects.raspberrypi.org/en/projects/get-started-pico-w/2 
from XRPLib.defaults import *
import network
import machine
from time import sleep
import time
from machine import Pin 
import usocket as socket

from STEM_Embassy.ColorSensor import TCS34725
from STEM_Embassy.TSEwebsocket import WebSocketClient


print("* Starting up ")

# VARS ------------------------------------------------------
ssid = "LiCe"
password ="12061206"

wsHost = "192.168.0.13"
wsPort = 8080
wsPath = "/ws"

pin = Pin("LED", Pin.OUT)

# INITS
ws = socket.socket()
#sensor = TCS34725()

# TESTING WS LIB
ws = WebSocketClient(wsHost, wsPort, wsPath)

# GENERAL FUNCS ----------------------------------------------
def cleanup():
    print("Cleaning up ")
    pin.off()
    if ws:
        ws.close()
    machine.reset()

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

# Actuators
def motor_control(data):
    if(data["w"] == True):
        drivetrain.set_effort(1, 1)
    elif(data["s"] == True):
        drivetrain.set_effort(-1, -1)
    elif(data["a"] == True):
        drivetrain.set_effort(0, 1)
    elif(data["d"] == True):    
        drivetrain.set_effort(1, 0)
    elif(data["w"] == True and data["a"] == True):
        drivetrain.set_effort(0.3, 1)
    elif(data["w"] == True and data["d"] == True):
        drivetrain.set_effort(1, 0.3)
    elif(data["w"] == False and data["s"] == False and data["a"] == False and data["d"] == False):
        drivetrain.set_effort(0, 0)

def setServo(data):
    servo_one.set_angle(data["servo"])

# SETUP  -----------------------------------------------------------
try:
    if not connect():
        print("* WiFi setup failed")
        sleep(5)
        cleanup()
        
    if not ws.connect():
        print("* WebSocket setup failed")
        sleep(5)
        cleanup()

    print("* Setup complete, entering main loop")
    print(" --------------------------------------------")
    
    # MAIN LOOP -----------------------------------------------------------    
    while True:
        message = ws.handle_websocket()
        
        if message is False:
            print("* Connection issue detected, cleaning up")
            cleanup()
        elif message is not None:
            motor_control(message)
            setServo(message)
            
        #r,g,b,c =  sensor.read_rgbc()

        
except KeyboardInterrupt:
    print("* Connection stopped by user")
except Exception as e:
    print(f"* Unexpected error: {e}")
    time.sleep(5)
finally:
    time.sleep(5)
    cleanup()
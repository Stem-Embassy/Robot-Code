# https://projects.raspberrypi.org/en/projects/get-started-pico-w/2 
import network
import machine
import struct
import os
from time import sleep
import time
from machine import Pin 
import usocket as socket
import asyncio

print("* Starting up ")

# VARS ------------------------------------------------------
ssid = 'KML-17-19'
password = 'driefelja32'

wsHost = "192.168.200.247"
wsPort = 8080
wsPath = "/ws"

pin = Pin("LED", Pin.OUT)

ws = socket.socket()
# GENERAL FUNCS ----------------------------------------------
def cleanup():
    print("Stopping and resetting everything")
    pin.off()
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

    while wlan.isconnected() == False:
        print(".")
        sleep(1) 
    
    print("* Wifi Connected!")   

# WS FUNCS -------------------------------------------------
def wsConnect():
    addr = socket.getaddrinfo(wsHost,wsPort)[0][-1]
    ws.connect(addr)

    handshake = (
        "GET {path} HTTP/1.1\r\n"
        "Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).format(path=wsPath, host=wsHost, port=wsPort)
    ws.send(handshake)

    # read response
    response = ws.recv(1024)
    if b"101 Switching Protocols" not in response:
        raise Exception("websocket handshake failed")
    
    print("* WS connected !")

def mask_payload(payload):
    """Generate a masking key and apply it to the payload."""
    mask_key = os.urandom(4)  # generate random 4-byte masking key
    masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return mask_key, masked_payload

def send_message( message, opcode=0x1):
    # prepare the websocket frame
    frame = bytearray()
    frame.append(0x80 | opcode)  # FIN + opcode (0x1 for text, 0x9 for ping 0xA for pong)
    
    payload = message.encode("utf-8") if isinstance(message, str) else message
    length = len(payload)
    
    if length <= 125:
        frame.append(0x80 | length)  # set MASK bit
    elif length <= 65535:
        frame.append(0x80 | 126)  # set MASK bit and indicate 16-bit length
        frame.extend(struct.pack(">H", length))
    else:
        raise ValueError("message too long")
    
    # mask the payload
    mask_key, masked_payload = mask_payload(payload)
    frame.extend(mask_key)  # add masking key
    frame.extend(masked_payload)  # add masked payload
    
    ws.send(frame)
    blink()

async def receive_message():
    # read the first byte (FIN + opcode)
    byte1 = ws.recv(1)[0]
    opcode = byte1 & 0x0F

    # read the second byte (MASK bit + payload length)
    byte2 = ws.recv(1)[0]
    mask = byte2 & 0x80
    length = byte2 & 0x7F

    if length == 126:
        length = struct.unpack(">H", ws.recv(2))[0]
    elif length == 127:
        raise Exception("unsupported frame length")
    
    if opcode not in (1, 10): 
        raise Exception("unsupported frame type")
    
    # read the mask key if present
    if mask:
        mask_key = ws.recv(4)
    else:
        mask_key = None
    
    # read the payload
    payload = ws.recv(length)
    if mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    if opcode == 0x9:  # Ping frame
        print("* Got a ping, sending a pong")
        send_message(payload.decode("utf-8"), opcode=0xA)  
        return None  
    
    return payload.decode("utf-8")


# SETUP  -----------------------------------------------------------
try:
    connect()
    wsConnect()

except KeyboardInterrupt:
    print("Connection stopped")

# MAIN LOOP -----------------------------------------------------------    
currentTime = time.time();
while True:
    
    try:
        send_message("Testing this from pi")
        response = receive_message()
        print("received:", response)
    except KeyboardInterrupt:
        break

cleanup()

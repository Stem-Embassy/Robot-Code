# https://projects.raspberrypi.org/en/projects/get-started-pico-w/2 
import network
import machine
import struct
import os
from time import sleep
import time
from machine import Pin 
import usocket as socket
import ujson

from XRPLib.defaults import *

print("* Starting up ")

# VARS ------------------------------------------------------
ssid = "LiCe"
password ="12061206"

wsHost = "192.168.0.13"
wsPort = 8080
wsPath = "/ws"

pin = Pin("LED", Pin.OUT)

ws = socket.socket()
last_ping_sent = 0
last_pong_received = 0
ping_interval = 15  # seconds, should match server's ping interval
pong_timeout = 20   # seconds, max time to wait for a pong response

# GENERAL FUNCS ----------------------------------------------
def cleanup():
    print("Stopping and resetting everything")
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

# WS FUNCS -------------------------------------------------
def wsConnect():
    ws.settimeout(5)  # Setting socket timeout for operations
    
    try:
        addr = socket.getaddrinfo(wsHost, wsPort)[0][-1]
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
        
        print("* WS connected!")
        return True
    except Exception as e:
        print(f"* WS connection error: {e}")
        return False

def mask_payload(payload):
    """Generate a masking key and apply it to the payload."""
    mask_key = os.urandom(4)  # generate random 4-byte masking key
    masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return mask_key, masked_payload

def send_message(message, opcode=0x1):
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
    
    try:
        ws.send(frame)
        if opcode == 0x9:  # If sending ping
            global last_ping_sent
            last_ping_sent = time.time()
            # print("* Ping sent")
        elif opcode == 0xA:  # If sending pong
            print("* Pong sent")
        elif opcode == 0x1:  # If sending text
            blink()
        return True
    except Exception as e:
        print(f"* Send error: {e}")
        return False

def receive_message(timeout=0.1):
    # Set a short timeout for non-blocking behavior
    ws.settimeout(timeout)
    
    try:
        # Read the first byte (FIN + opcode)
        data = ws.recv(1)
        if not data:  # Connection closed
            return False
        
        byte1 = data[0]
        opcode = byte1 & 0x0F

        # Read the second byte (MASK bit + payload length)
        data = ws.recv(1)
        if not data:
            return False
        
        byte2 = data[0]
        mask = byte2 & 0x80
        length = byte2 & 0x7F

        if length == 126:
            length = struct.unpack(">H", ws.recv(2))[0]
        elif length == 127:
            raise Exception("unsupported frame length")
        
        # Read the mask key if present
        if mask:
            mask_key = ws.recv(4)
        else:
            mask_key = None
        
        # Read the payload
        payload = ws.recv(length) if length > 0 else b''
        if mask_key and payload:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        # Handle control frames
        if opcode == 0x8:  # Close frame
            print("* Received close frame")
            return False
        elif opcode == 0x9:  # Ping frame
            # print("* Received ping, sending pong")
            send_message(payload, opcode=0xA)  # Send pong with the same payload
            return None  # Continue receiving
        elif opcode == 0xA:  # Pong frame
            # print("* Received pong")
            global last_pong_received
            last_pong_received = time.time()
            return None  # Continue receiving
        elif opcode == 0x1 or opcode == 0x2:  # Text or binary frame
            return payload.decode("utf-8") if opcode == 0x1 else payload
        else:
            print(f"* Unsupported opcode: {opcode}")
            return None
            
    except OSError as e:
        # Socket timeout is expected (no data available)
        if e.args[0] == 110:  # ETIMEDOUT
            return None
        print(f"* Receive error: {e}")
        return False  # Indicate connection issue
    except Exception as e:
        print(f"* Unexpected receive error: {e}")
        return False

def check_connection():
    # Check if we should send a ping (heartbeat)
    current_time = time.time()
    
    # Send ping every ping_interval
    if current_time - last_ping_sent > ping_interval:
        if not send_message("heartbeat", opcode=0x9):
            return False
    
    # Check for pong timeout
    if last_ping_sent > 0 and last_pong_received < last_ping_sent and current_time - last_ping_sent > pong_timeout:
        print("* Pong timeout - connection may be dead")
        return False
        
    return True

def handle_websocket():
    # Process any incoming messages
    for _ in range(5):  # Check a few times for any pending messages
        message = receive_message(timeout=0.1)
        
        if message is False:  # Connection issue
            return False
        elif message is not None:  # Actual message received
            #print(f"* Received: {message}")
            try:
                # Check if message is bytes or string and handle accordingly
                if isinstance(message, bytes):
                    json_data = ujson.loads(message.decode("utf-8"))
                    motor_control(json_data)
                    setServo(json_data)
                else:
                    json_data = ujson.loads(message)
                    motor_control(json_data)
                    setServo(json_data)
                
                #print(f"* Parsed JSON: {json_data}")
                
            except ValueError as e:
                pass
    
    # Check connection health
    if not check_connection():
        return False
        
    return True

# MOTOR CONTROLS

def motor_control(data):
    if(data["w"] == True):
        #print("Moving forward")
        drivetrain.set_effort(1, 1)
    elif(data["s"] == True):
        drivetrain.set_effort(-1, -1)
    elif(data["a"] == True):
        #print("Turning left")
        drivetrain.set_effort(0, 1)
    elif(data["d"] == True):    
        #print("Turning right")
        drivetrain.set_effort(1, 0)
    elif(data["w"] == True and data["a"] == True):
        drivetrain.set_effort(0.3, 1)
    elif(data["w"] == True and data["d"] == True):
        drivetrain.set_effort(1, 0.3)
    elif(data["w"] == False and data["s"] == False and data["a"] == False and data["d"] == False):
        # print("Stopping")
        drivetrain.set_effort(0, 0)

def setServo(angle):
    print(angle["servo"])
    servo_one.set_angle(angle["servo"])

# SETUP  -----------------------------------------------------------
try:
    if not connect():
        print("* WiFi setup failed")
        time.sleep(5)
        cleanup()
        
    if not wsConnect():
        print("* WebSocket setup failed")
        time.sleep(5)
        cleanup()

    print("* Setup complete, entering main loop")
    last_message_time = 0
    message_interval = 30  # seconds between test messages
    
    # Initialize ping/pong tracking
    last_ping_sent = time.time()
    last_pong_received = time.time()

    # MAIN LOOP -----------------------------------------------------------    
    while True:
        # Process WebSocket communications
        if not handle_websocket():
            print("* Connection lost, attempting to reconnect")
            ws.close()
            if not wsConnect():
                print("* Reconnection failed")
                break
            last_ping_sent = time.time()
            last_pong_received = time.time()
            continue
        
        # Send test message periodically
        current_time = time.time()
        if current_time - last_message_time > message_interval:
            if send_message("Testing this from pi"):
                last_message_time = current_time
            else:
                print("* Failed to send message")
                break
        
        # Small delay to prevent tight loop
        sleep(0.1)
        
except KeyboardInterrupt:
    print("* Connection stopped by user")
except Exception as e:
    print(f"* Unexpected error: {e}")
finally:
    cleanup()
# https://projects.raspberrypi.org/en/projects/get-started-pico-w/2
from XRPLib.defaults import *
import network
import machine
from time import sleep
import time
from machine import Pin
import usocket as socket
import json



try:
    from STEM_Embassy.ColorSensor import TCS34725

    try:
        sensor = TCS34725()
        sensor.set_integration_time(24)
        sensor.set_gain(4)
    #  print("* Color sensor found!")
    except Exception as e:
        #  print("* Color sensor not found, try installing it in the [range] pinout")
        sensor = None
        pass
except ImportError as e:
    sensor = None
    pass
from STEM_Embassy.TSEwebsocket import WebSocketClient

pin = Pin("LED", Pin.OUT)

def blink():
    print("Blinking")
    pin.toggle()
    sleep(0.5)
    pin.toggle()
blink()
blink()
blink()

print("* Starting up ")

# VARS ------------------------------------------------------
ssid = "D!AZ"  # TP-LINK_1F4A
password = "J@nuary22001"  # 36505401

wsHost = "192.168.86.69"  # 192.168.0.159
wsPort = 8080
wsPath = "/ws"



ws = socket.socket()


# TESTING WS LIB
ws = WebSocketClient(wsHost, wsPort, wsPath)


# GENERAL FUNCS ----------------------------------------------
def cleanup():
    #  print("Stopping and resetting everything")
    pin.off()
    if ws:
        ws.close()
    machine.reset()




# WIFI FUNCS --------------------------------------------------
def connect():
    wlan = None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    #  print("* Waiting for WiFi connection...")

    max_wait = 30
    while max_wait > 0:
        if wlan.isconnected():
            break
        max_wait -= 1
        #  print(".", end="")
        sleep(1)

    if wlan.isconnected():
        blink()
        #  print("\n* Wifi Connected!")
        #  print(f"* IP Address: {wlan.ifconfig()[0]}")
        return True
    else:
        #  print("\n* WiFi connection failed!")
        return False


# Actuators
def motor_control(data):
    if "type" not in data:
        return
    effort = 1
    if "effort" in data:
        effort = data["effort"]
    w, a, s, d = data["w"], data["a"], data["s"], data["d"]
    if data["type"] == "keyboard":
        if w and a:
            drivetrain.set_effort(0.3 * effort, 1 * effort)
        elif w and d:
            drivetrain.set_effort(1 * effort, 0.3 * effort)
        elif s and a:
            drivetrain.set_effort(-0.3 * effort, -1 * effort)
        elif s and d:
            drivetrain.set_effort(-1 * effort, -0.3 * effort)
        elif w:
            drivetrain.set_effort(1 * effort, 1 * effort)
        elif s:
            drivetrain.set_effort(-1 * effort, -1 * effort)
        elif a:
            drivetrain.set_effort(0 * effort, 1 * effort)
        elif d:
            drivetrain.set_effort(1 * effort, 0 * effort)
        else:
            drivetrain.set_effort(0, 0)
    if data["type"] == "joystick":
        #  print(data)
        # Extract joystick x and y values with default values if not present
        x = data.get("x", 0)  # Left/right; -1 = full left, 1 = full right
        y = data.get("y", 0)  # Forward/backward; -1 = full back, 1 = full forward

        # Optionally limit the range (in case input is noisy or unbounded)
        x = max(-1, min(1, x))
        y = max(-1, min(1, y))

        # Calculate motor efforts for differential drive
        left_effort = y + x
        right_effort = y - x

        # Normalize the output to be within [-1, 1]
        max_effort = max(abs(left_effort), abs(right_effort), 1)
        left_effort /= max_effort
        right_effort /= max_effort

        # Apply to drivetrain
        drivetrain.set_effort(left_effort, right_effort)


last_servo_position = 0


def setServo(data):
    global last_servo_position
    # Check if servo value exists in data
    if "servo" in data:
        target_position = data["servo"]
        # If positions are different, gradually move to new position
        if target_position != last_servo_position:
            # Determine direction and step size
            step = 1 if target_position > last_servo_position else -1
            # Move in small increments
            current = last_servo_position
            while current != target_position:
                current += step
                # Stop at target position
                if (step > 0 and current > target_position) or (
                    step < 0 and current < target_position
                ):
                    current = target_position
                servo_one.set_angle(current)
                sleep(0.01)  # Small delay for smooth movement
            # Update last position
            last_servo_position = target_position


# Send message to (web socket's) server api endpoint
def send_log_message(message):
    try:
        # Setup for both health-check and log sending
        api_host = wsHost
        api_port = wsPort
        health_path = "/health-check"
        log_path = "/send-log"

        # Step 1: Check health-check endpoint
        health_request = (
            f"GET {health_path} HTTP/1.1\r\n"
            f"Host: {api_host}:{api_port}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        addr = socket.getaddrinfo(api_host, api_port)[0][-1]
        s = socket.socket()
        s.connect(addr)
        s.send(health_request.encode())
        response = s.recv(1024).decode()
        s.close()

        if "200 OK" not in response:
            #  print("* Health check failed")
            connect()
            # reset the wifi and then reconnect

            # return

        #  print("* Health check passed")

        # Step 2: Send log to /send-log
        payload = json.dumps({"log": message})
        log_request = (
            f"POST {log_path} HTTP/1.1\r\n"
            f"Host: {api_host}:{api_port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{payload}"
        )

        s = socket.socket()
        s.connect(addr)
        s.send(log_request.encode())
        log_response = s.recv(1024).decode()
        s.close()

    #  print("* Log message sent. Server response:")
    #  print(log_response)

    except Exception as e:
        #  print(f"* Failed to send log message: {e}")
        pass


# SETUP  -----------------------------------------------------------
try:
    if not connect():
        #  print("* WiFi setup failed")
        sleep(5)
        cleanup()

    if not ws.connect():
        #  print("* WebSocket setup failed")
        sleep(5)
        cleanup()
    else:
        ws.send_message(json.dumps({"client": "Robot"}))

    #  print("* Setup complete, entering main loop")
    blink()
    blink()
    # MAIN LOOP -----------------------------------------------------------

    # Track last time we sent color data
    last_color_send = time.time()
    color_send_interval = 0.5  # Send every 0.5 seconds

    # Track WebSocket reconnection attempts
    last_reconnect_attempt = 0
    reconnect_interval = 5  # Wait 5 seconds between reconnection attempts
    max_reconnect_attempts = 1000  # Maximum number of consecutive reconnection attempts

    # Track the number of reconnect attempts
    reconnect_attempts = 0

    # set the pin of rangefinder to 22 and echo_pin to 28, this is the [extra] pinout
    try:
        if sensor is not None:
            rangefinder = Rangefinder(22, 28)  # [extra] pinout
        else:
            rangefinder = Rangefinder(20, 21)  # [range] pinout
            pass
    except Exception as e:
        # print(f"* Error setting up rangefinder: {e}")
        rangefinder = None

    reconnect_attempts = 0
    while True:
        data_payload = {}
        # Handle incoming messages (motor control)
        message = ws.handle_websocket()

        # Check if it's time to send color data
        current_time = time.time()
        if current_time - last_color_send >= color_send_interval:
            try:
                if sensor is not None:
                    # Read raw color data
                    r, g, b, c = sensor.read_rgbc()

                    # Normalize to 0-255 range
                    if c > 0:  # Avoid division by zero
                        r_norm = min(255, int((r / c) * 255))
                        g_norm = min(255, int((g / c) * 255))
                        b_norm = min(255, int((b / c) * 255))
                    else:
                        r_norm, g_norm, b_norm = 0, 0, 0

                    # Add normalized color to data_payload
                    data_payload["red"] = r_norm
                    data_payload["green"] = g_norm
                    data_payload["blue"] = b_norm

                    # You can also send raw values if needed
                    data_payload["raw_red"] = r
                    data_payload["raw_green"] = g
                    data_payload["raw_blue"] = b
                    data_payload["raw_clear"] = c
                    # add color to data_payload
                    data_payload["red"] = r
                    data_payload["green"] = g
                    data_payload["blue"] = b

                if rangefinder is not None:
                    # Get range finder data
                    distance = rangefinder.distance()
                    data_payload["distance"] = distance

                # Send data_payload if WebSocket is connected
                # print(data_payload)
                # if ws.is_connected():
                ws.send_message(json.dumps(data_payload))

                last_color_send = current_time  # Update the last send time
            except Exception as e:
                #  print(f"* Error sending color data: {e}")
                pass

        # Check if WebSocket is disconnected
        if message is False:
            # Check reconnection logic
            current_time = time.time()
            if current_time - last_reconnect_attempt >= reconnect_interval:
                last_reconnect_attempt = current_time
                reconnect_attempts += 1

                if reconnect_attempts <= max_reconnect_attempts:
                    blink()  # Visual indicator of reconnection attempt
                    ws.close()  # Close the current WebSocket
                    if ws.connect():  # Try to reconnect
                        reconnect_attempts = 0  # Reset reconnection counter on success
                        ws.send_message(json.dumps({"client": "Robot"}))
                    else:

                        # Log when reconnection fails and it's still trying
                        send_log_message("WebSocket connection lost, retrying...")
                        ws = None  # Reset WebSocket object
                        ws = WebSocketClient(wsHost, wsPort, wsPath)
                        ws.connect()
                        sleep(5)  # Wait before trying again
                else:
                    # Maximum attempts reached, notify the server
                    send_log_message(
                        "Max WebSocket reconnection attempts reached, server may be down."
                    )
                    cleanup()  # Reset and exit
        elif message is not None:
            # Reset reconnection counter when we receive messages successfully
            reconnect_attempts = 0
            try:
                # Check if message is already a dictionary
                if isinstance(message, dict):
                    data = message
                else:
                    # Try to decode if it's bytes
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    # Parse JSON string to dictionary
                    data = json.loads(message)

                motor_control(data)
                setServo(data)
            except Exception as e:
                # get type
                #  print(type(message))
                #  print(f"* Error handling message: {e}")
                # print(f"* Message type: {type(message)}")
                continue


except KeyboardInterrupt:
    # print("* Connection stopped by user")
    pass
except Exception as e:
    # print(f"* Unexpected error: {e}")
    time.sleep(5)
finally:
    time.sleep(5)
    cleanup()


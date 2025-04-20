import network
import machine
import struct
import os
from time import sleep
import time
from machine import Pin 
import usocket as socket


class WebSocketClient:
    def __init__(self, host, port, path="/ws", ping_interval=15, pong_timeout=20):
        self.host = host
        self.port = port
        self.path = path
        self.socket = None
        self.last_ping_sent = 0
        self.last_pong_received = 0
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        self.connected = False

    def connect(self):
        try:
            # Close any existing socket
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                    
            # Create a new socket
            self.socket = socket.socket()
            
            # Set timeout before connection
            try:
                self.socket.settimeout(5.0)
            except:
                # If settimeout doesn't work, try alternative approach
                try:
                    self.socket.setblocking(False)
                    # We'll handle timeouts manually in the receive logic
                except:
                    print("* Warning: Could not set socket timeout or blocking mode")
            
            addr = socket.getaddrinfo(self.host, self.port)[0][-1]
            self.socket.connect(addr)

            handshake = (
                "GET {path} HTTP/1.1\r\n"
                "Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).format(path=self.path, host=self.host, port=self.port)
            self.socket.send(handshake)

            # Read response
            response = self.socket.recv(1024)
            if b"101 Switching Protocols" not in response:
                raise Exception("websocket handshake failed")
            
            print("* WS connected!")
            self.connected = True
            self.last_ping_sent = time.time()
            self.last_pong_received = time.time()
            return True
        except Exception as e:
            print(f"* WS connection error: {e}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False

    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.connected = False
        self.socket = None

    def _mask_payload(self, payload):
        """Generate a masking key and apply it to the payload."""
        mask_key = os.urandom(4)  # generate random 4-byte masking key
        masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return mask_key, masked_payload

    def send_message(self, message, opcode=0x1):
        if not self.connected or not self.socket:
            return False
            
        # Prepare the websocket frame
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
        
        # Mask the payload
        mask_key, masked_payload = self._mask_payload(payload)
        frame.extend(mask_key)  # add masking key
        frame.extend(masked_payload)  # add masked payload
        
        try:
            self.socket.send(frame)
            if opcode == 0x9:  # If sending ping
                self.last_ping_sent = time.time()
                print("* Ping sent")
            elif opcode == 0xA:  # If sending pong
                print("* Pong sent")
            return True
        except Exception as e:
            print(f"* Send error: {e}")
            self.connected = False
            return False

    def receive_message(self, timeout=0.1):
        if not self.connected or not self.socket:
            return False

        # Using a non-blocking approach with timeout handling
        start_time = time.time()

        try:
            # Try to read the first byte with timeout
            while time.time() - start_time < timeout:
                try:
                    # Read the first byte (FIN + opcode)
                    data = self.socket.recv(1)
                    if data:  # If we got data, process it
                        break
                except OSError as e:
                    # Expected timeout error in non-blocking mode
                    if e.args[0] == 11:  # EAGAIN
                        sleep(0.01)  # Small delay to prevent tight loop
                        continue
                    raise  # Re-raise other errors

                sleep(0.01)  # Small delay to prevent tight loop

            # If we timed out waiting for data
            if time.time() - start_time >= timeout:
                return None

            if not data:  # Connection closed
                self.connected = False
                return False

            byte1 = data[0]
            opcode = byte1 & 0x0F

            # Read the second byte (MASK bit + payload length)
            data = self.socket.recv(1)
            if not data:
                self.connected = False
                return False

            byte2 = data[0]
            mask = byte2 & 0x80
            length = byte2 & 0x7F

            if length == 126:
                length = struct.unpack(">H", self.socket.recv(2))[0]
            elif length == 127:
                raise Exception("unsupported frame length")

            # Read the mask key if present
            if mask:
                mask_key = self.socket.recv(4)
            else:
                mask_key = None

            # Read the payload
            payload = self.socket.recv(length) if length > 0 else b''
            if mask_key and payload:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            # Handle control frames
            if opcode == 0x8:  # Close frame
                print("* Received close frame")
                self.connected = False
                return False
            elif opcode == 0x9:  # Ping frame
                print("* Received ping, sending pong")
                self.send_message(payload, opcode=0xA)  # Send pong with the same payload
                return None  # Continue receiving
            elif opcode == 0xA:  # Pong frame
                print("* Received pong")
                self.last_pong_received = time.time()
                return None  # Continue receiving
            elif opcode == 0x1:  # Text frame
                return payload.decode("utf-8")  # Return the decoded text message
            else:
                print(f"* Unsupported opcode: {opcode}")
                return None

        except OSError as e:
            # Handle various socket errors
            if e.args[0] in (11, 110):  # EAGAIN or ETIMEDOUT
                return None
            print(f"* Receive error: {e}")
            self.connected = False
            return False  # Indicate connection issue
        except Exception as e:
            print(f"* Unexpected receive error: {e}")
            self.connected = False
            return False

    def check_connection(self):
        if not self.connected or not self.socket:
            return False
            
        # Check if we should send a ping (heartbeat)
        current_time = time.time()
        
        # Send ping every ping_interval
        if current_time - self.last_ping_sent > self.ping_interval:
            if not self.send_message("heartbeat", opcode=0x9):
                return False
        
        # Check for pong timeout
        if self.last_ping_sent > 0 and self.last_pong_received < self.last_ping_sent and current_time - self.last_ping_sent > self.pong_timeout:
            print("* Pong timeout - connection may be dead")
            return False
            
        return True

    def handle(self):
        if not self.connected or not self.socket:
            return False
            
        # Process any incoming messages
        for _ in range(5):  # Check a few times for any pending messages
            message = self.receive_message(timeout=0.1)
            
            if message is False:  # Connection issue
                return False
            elif message is not None:  # Actual message received
                print(f"* Received: {message}")
                # You could call a callback here if you wanted
        
        # Check connection health
        if not self.check_connection():
            return False
            
        return True
import socket
import struct
import os
import time
import ujson


class WebSocketClient:
    def __init__(self, host, port, path):
        self.wsHost = host
        self.wsPort = port
        self.wsPath = path
        self.ws = socket.socket()
        self.ping_interval = 30  # seconds
        self.pong_timeout = 10   # seconds
        self.last_ping_sent = 0
        self.last_pong_received = 0
        
    def connect(self):
        """Establish WebSocket connection with handshake."""
        self.ws.settimeout(5)
        
        try:
            addr = socket.getaddrinfo(self.wsHost, self.wsPort)[0][-1]
            self.ws.connect(addr)

            handshake = (
                "GET {path} HTTP/1.1\r\n"
                "Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).format(path=self.wsPath, host=self.wsHost, port=self.wsPort)
            self.ws.send(handshake)

            # read response
            response = self.ws.recv(1024)
            if b"101 Switching Protocols" not in response:
                raise Exception("websocket handshake failed")
            
            print("* WS connected!")
            return True
        except Exception as e:
            print(f"* WS connection error: {e}")
            return False

    def close(self):
        self.ws.close()
        
    def mask_payload(self, payload):
        """Generate a masking key and apply it to the payload."""
        mask_key = os.urandom(4)  # generate random 4-byte masking key
        masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return mask_key, masked_payload

    def send_message(self, message, opcode=0x1):
        """Send a message with the specified opcode."""
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
        mask_key, masked_payload = self.mask_payload(payload)
        frame.extend(mask_key)  # add masking key
        frame.extend(masked_payload)  # add masked payload
        
        try:
            self.ws.send(frame)
            if opcode == 0x9:  # If sending ping
                self.last_ping_sent = time.time()
                # print("* Ping sent")
            elif opcode == 0xA:  # If sending pong
                pass
            elif opcode == 0x1:  # If sending text
                pass
            return True
        except Exception as e:
            #print(f"* Send error: {e}")
            return False

    def receive_message(self, timeout=0.1):
        """Receive and decode a WebSocket message."""
        # Set a short timeout for non-blocking behavior
        self.ws.settimeout(timeout)
        
        try:
            # Read the first byte (FIN + opcode)
            data = self.ws.recv(1)
            if not data:  # Connection closed
                return False
            
            byte1 = data[0]
            opcode = byte1 & 0x0F

            # Read the second byte (MASK bit + payload length)
            data = self.ws.recv(1)
            if not data:
                return False
            
            byte2 = data[0]
            mask = byte2 & 0x80
            length = byte2 & 0x7F

            if length == 126:
                length = struct.unpack(">H", self.ws.recv(2))[0]
            elif length == 127:
                raise Exception("unsupported frame length")
            
            # Read the mask key if present
            if mask:
                mask_key = self.ws.recv(4)
            else:
                mask_key = None
            
            # Read the payload
            payload = self.ws.recv(length) if length > 0 else b''
            if mask_key and payload:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            # Handle control frames
            if opcode == 0x8:  # Close frame
                #print("* Received close frame")
                return False
            elif opcode == 0x9:  # Ping frame
                # print("* Received ping, sending pong")
                self.send_message(payload, opcode=0xA)  # Send pong with the same payload
                return None  # Continue receiving
            elif opcode == 0xA:  # Pong frame
                # print("* Received pong")
                self.last_pong_received = time.time()
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
            #print(f"* Receive error: {e}")
            return False  # Indicate connection issue
        except Exception as e:
            #print(f"* Unexpected receive error: {e}")
            return False

    def check_connection(self):
        """Check WebSocket connection health with ping/pong mechanism."""
        current_time = time.time()
        
        # Send ping every ping_interval
        if current_time - self.last_ping_sent > self.ping_interval:
            if not self.send_message("heartbeat", opcode=0x9):
                return False
        
        # Check for pong timeout
        if (self.last_ping_sent > 0 and 
            self.last_pong_received < self.last_ping_sent and 
            current_time - self.last_ping_sent > self.pong_timeout):
            #print("* Pong timeout - connection may be dead")
            return False
            
        return True

    def handle_websocket(self):
        """Process incoming messages and check connection health.
        Returns:
            - False if connection issue
            - String if valid JSON message received
            - None if no message but connection is fine
        """
        # Process any incoming messages
        for _ in range(5):  # Check a few times for any pending messages
            message = self.receive_message(timeout=0.1)
            
            if message is False:  # Connection issue
                return False
            elif message is not None:  # Actual message received
                try:
                    # Check if message is bytes or string and handle accordingly
                    if isinstance(message, bytes):
                        json_data = ujson.loads(message.decode("utf-8"))
                    else:
                        json_data = ujson.loads(message)
                    
                    # Here, we'll return the string form of the JSON data
                    # You can customize this to return specific fields from json_data
                    return json_data
                    
                except ValueError as e:
                    # If JSON parsing fails, continue to next iteration
                    pass
        
        # Check connection health
        if not self.check_connection():
            return False
        
        # If no message was received but connection is fine, return None
        return None





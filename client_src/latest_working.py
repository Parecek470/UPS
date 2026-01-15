import sys
import socket
import selectors
import threading
import queue
import time
import tkinter as tk
from tkinter import messagebox

# ==============================================================================
# 1) NETWORK LAYER
# Responsibilities: Socket management, select/poll loop, byte stream reassembly
# ==============================================================================
class NetworkClient:
    """
    Handles low-level TCP socket operations using a selector-based event loop.
    Runs in its own thread to ensure non-blocking I/O.
    """
    def __init__(self, host, port, incoming_callback, tick_callback):
        self.host = host
        self.port = port
        self.incoming_callback = incoming_callback  # Function to call with complete msgs
        self.tick_callback = tick_callback          # Function to call for logic updates (timers)
        
        self._selector = selectors.DefaultSelector() # Auto-selects best polling method (poll/epoll/select)
        self._socket = None
        self._send_queue = queue.Queue()
        self._running = False
        self._thread = None
        
        # Buffer for stream reassembly
        self._recv_buffer = b""

    def start(self):
        """Initializes the socket and starts the background I/O thread."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setblocking(False) # Essential for select/poll
            self._socket.connect_ex((self.host, self.port)) # Async connect
            
            # Register socket for READ and WRITE events
            self._selector.register(
                self._socket, 
                selectors.EVENT_READ | selectors.EVENT_WRITE, 
                data=None
            )
            
            self._running = True
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()
            return True, "Network thread started."
        except Exception as e:
            return False, f"Socket creation failed: {e}"

    def send_message(self, message):
        """Queues a message to be sent over the socket."""
        # Append newline as protocol delimiter if missing
        if not message.endswith('\n'):
            message += '\n'
        self._send_queue.put(message.encode('utf-8'))

    def _run_event_loop(self):
        """
        The main blocking loop (single-threaded concurrency).
        Uses select/poll to multiplex I/O and handle logic ticks.
        """
        while self._running:
            # 1. Logic Tick: Allow Protocol layer to check timeouts
            if self.tick_callback:
                self.tick_callback()

            # 2. Select: Wait for I/O events with a short timeout
            # Timeout ensures we don't block forever and can process the send_queue/timers
            events = self._selector.select(timeout=0.1)

            for key, mask in events:
                if mask & selectors.EVENT_READ:
                    self._handle_read()
                if mask & selectors.EVENT_WRITE:
                    self._handle_write()

    def _handle_read(self):
        """Reads raw bytes, handles reassembly, emits complete lines."""
        try:
            data = self._socket.recv(4096)
            if data:
                self._recv_buffer += data
                # Message Reassembly Logic:
                # We split by newline. The last element is the "remainder" 
                # (incomplete message) which goes back into the buffer.
                if b'\n' in self._recv_buffer:
                    lines = self._recv_buffer.split(b'\n')
                    # The last part is incomplete or empty; save it
                    self._recv_buffer = lines[-1]
                    
                    # Process all complete parts
                    for line in lines[:-1]:
                        msg_str = line.decode('utf-8', errors='ignore')
                        self.incoming_callback(msg_str)
            else:
                # Empty data means server closed connection
                self._close_connection("Server closed connection")
        except BlockingIOError:
            pass # Socket not ready
        except Exception as e:
            self._close_connection(f"Read error: {e}")

    def _handle_write(self):
        """Checks send queue and writes to socket."""
        try:
            # We assume non-blocking socket is writable. 
            # In a robust app, we should check specifically if we have data to write
            # before selecting on WRITE, but for boilerplate, this checks queue.
            while not self._send_queue.empty():
                try:
                    msg_bytes = self._send_queue.get_nowait()
                    self._socket.sendall(msg_bytes)
                except queue.Empty:
                    break
        except Exception as e:
            self._close_connection(f"Write error: {e}")

    def _close_connection(self, reason):
        print(f"DEBUG: Connection closed: {reason}")
        self._running = False
        try:
            self._selector.unregister(self._socket)
            self._socket.close()
        except:
            pass

# ==============================================================================
# 2) PROTOCOL / CONTROL LAYER
# Responsibilities: Protocol validation, ACK tracking, Retry logic, State
# ==============================================================================
class ProtocolController:
    """
    Manages the 'BJ:' protocol logic.
    Decoupled from socket details; interacts via callbacks and queues.
    """
    def __init__(self, gui_queue):
        self.gui_queue = gui_queue # Queue to send events to GUI
        self.network = None        # Reference to NetworkLayer (set later)
        
        # State for ACK tracking
        self.pending_msg = None
        self.last_send_time = 0
        self.retry_count = 0
        self.waiting_for_ack = False
        
        # Constants
        self.TIMEOUT_SEC = 5.0
        self.MAX_RETRIES = 3

    def set_network(self, network_layer):
        self.network = network_layer

    def send_nickname_request(self, nickname):
        """Initiates the handshake logic."""
        payload = f"BJ:LOGIN___:{nickname}"
        self._send_with_ack_logic(payload)
        self._notify_gui(f"Sending: {payload}")

    def send_join_room_request(self, room_name):
        payload = f"BJ:JOIN____:{room_name}"
        self._send_with_ack_logic(payload)
        self._notify_gui(f"Sending: {payload}")

    def send_fire_and_forget(self, payload): #send without ack
        if self.network:
            self.network.send_message(payload)

    def _send_with_ack_logic(self, payload): #send message and wait for ack, will try to resend if no ack
        self.pending_msg = payload
        self.retry_count = 0
        self.waiting_for_ack = True
        self.last_send_time = time.time()
        
        if self.network:
            self.network.send_message(payload)

    def on_network_message(self, raw_msg):
        """
        Called by NetworkLayer when a complete line is received.
        Validates protocol and handles ACKs.
        """
        # 1. Validate Protocol
        if not raw_msg.startswith("BJ:"):
            # Invalid message safely discarded
            print(f"DEBUG: Discarding invalid protocol message: {raw_msg}")
            return

        # 2. Process Valid Message
        content = raw_msg[3:].strip() # Remove "BJ:"
        
        # Check if it is an ACK (Server sends "BJ:ACK")
        if content == "ACK_____" and self.waiting_for_ack:
            self.waiting_for_ack = False
            self.pending_msg = None
            self._notify_gui("SUCCESS: ACK Received from Server.")
        else:
            self._notify_gui(f"Server says: {content}")

    def on_tick(self):
        """
        Called periodically by the Network Loop to handle timeouts.
        This runs in the BACKGROUND thread.
        """
        if self.waiting_for_ack and self.pending_msg:
            now = time.time()
            if (now - self.last_send_time) > self.TIMEOUT_SEC:
                if self.retry_count < self.MAX_RETRIES:
                    # RETRY LOGIC
                    self.retry_count += 1
                    self.last_send_time = now
                    print(f"DEBUG: Timeout. Resending ({self.retry_count}/{self.MAX_RETRIES})...")
                    self._notify_gui(f"Timeout. Retry {self.retry_count}...")
                    
                    if self.network:
                        self.network.send_message(self.pending_msg)
                else:
                    # FAILURE LOGIC
                    self.waiting_for_ack = False
                    self.pending_msg = None
                    self._notify_gui("FAILURE: Max retries reached. No ACK.")

    def _notify_gui(self, message):
        """Puts a message onto the GUI-safe queue."""
        self.gui_queue.put(message)

# ==============================================================================
# 3) GUI LAYER
# Responsibilities: Tkinter interface, Event Consumer, No freezing
# ==============================================================================
class ChatGUI:
    def __init__(self, root, host, port):
        self.root = root
        self.root.title(f"Python Client - {host}:{port}")
        self.root.geometry("400x300")

        # Config
        self.host = host
        self.port = port
        
        # Safe Queue for cross-thread communication (Protocol -> GUI)
        self.gui_event_queue = queue.Queue()

        # Initialize Layers
        self.protocol = ProtocolController(self.gui_event_queue)
        self.network = NetworkClient(
            self.host, 
            self.port, 
            incoming_callback=self.protocol.on_network_message,
            tick_callback=self.protocol.on_tick
        )
        self.protocol.set_network(self.network)

        self._init_ui()
        self._start_network()
        
        # Start GUI Queue Consumer
        self.root.after(100, self._process_gui_queue)

    def _init_ui(self):
        # Container
        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Status Label
        self.lbl_status = tk.Label(frame, text="Status: Disconnected", fg="grey")
        self.lbl_status.pack(pady=(0, 10))

        # Nickname Input
        tk.Label(frame, text="Enter Nickname:").pack(anchor="w")
        self.ent_nick = tk.Entry(frame)
        self.ent_nick.pack(fill=tk.X, pady=5)
        self.ent_nick.insert(0, "User1")

        # Connect/Send Button
        self.btn_send = tk.Button(frame, text="Send Nickname", command=self._on_send_click)
        self.btn_send.pack(pady=10)

        # Log Area
        self.txt_log = tk.Text(frame, height=10, state='disabled')
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def _start_network(self):
        success, msg = self.network.start()
        if success:
            self._log(f"System: {msg}")
            self.lbl_status.config(text="Status: Connected", fg="green")
        else:
            self._log(f"System Error: {msg}")
            self.lbl_status.config(text="Status: Error", fg="red")
            self.btn_send.config(state='disabled')

    def _on_send_click(self):
        """GUI Callback: Triggers Protocol layer logic."""
        nick = self.ent_nick.get().strip()
        if not nick:
            messagebox.showwarning("Input", "Nickname cannot be empty.")
            return
        
        # Hand off to Protocol Layer - Non-blocking
        self.protocol.send_nickname_request(nick)

    def _process_gui_queue(self):
        """
        Periodically checks the queue for messages from the Protocol Layer.
        This keeps the GUI responsive while receiving data from background threads.
        """
        try:
            while True:
                # Non-blocking pop
                msg = self.gui_event_queue.get_nowait()
                self._log(msg)
        except queue.Empty:
            pass
        finally:
            # Reschedule check
            self.root.after(100, self._process_gui_queue)

    def _log(self, text):
        """Thread-safe update of text widget."""
        self.txt_log.config(state='normal')
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state='disabled')

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    if len(sys.argv) != 3:
        # Default for quick testing if args missing
        print("Usage: python client.py <IP> <PORT>")
        print("Using defaults: 127.0.0.1 8888")
        server_ip = "127.0.0.1"
        server_port = 8888
    else:
        server_ip = sys.argv[1]
        try:
            server_port = int(sys.argv[2])
        except ValueError:
            print("Error: Port must be an integer.")
            sys.exit(1)

    root = tk.Tk()
    app = ChatGUI(root, server_ip, server_port)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Client shutting down...")
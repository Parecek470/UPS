import socket
import selectors
import threading
import queue
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

    def reconnect(self):
        """Cleanly closes current connection and reconnects."""
        # Stop current connection
        self._running = False
        try:
            if self._socket:
                self._selector.unregister(self._socket)
                self._socket.close()
        except:
            pass
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        
        # Reset state
        self._socket = None
        self._recv_buffer = b""
        
        # Start fresh connection
        return self.start()

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
            data = self._socket.recv(512)
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
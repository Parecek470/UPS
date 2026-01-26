"""BlackJack Client Application - Data management and validation Layer"""
"""author: Marek Manzel"""
""" responsibilities: Protocol logic, message validation, ACK tracking """
import time

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

        # connection to server variables
        self.last_message_time = time.time()
        self.invalid_msg_count = 0
        self.reconnect_atmpt = 0
        self.connected = False

    def set_network(self, network_layer):
        self.network = network_layer

    def send_nickname_request(self, nickname):
        """Initiates the handshake logic."""
        payload = f"BJ:LOGIN___:{nickname}"
        self._send_with_ack_logic(payload)
        print(f"Sending: {payload}")

    def send_join_room_request(self, room_name):
        payload = f"BJ:JOIN____:{room_name}"
        self._send_with_ack_logic(payload)
        print(f"Sending: {payload}")

    def send_leave_room_request(self):
        payload = "BJ:LVRO____"
        self._send_with_ack_logic(payload)
        print(f"Sending: {payload}")

    def send_play_again_signal(self):
        payload = "BJ:PAG_____"
        self.send_fire_and_forget(payload)
        print(f"Sending: {payload}")

    def send_hit_signal(self):
        payload = "BJ:HIT_____"
        self.send_fire_and_forget(payload)
        print(f"Sending: {payload}")

    def send_stand_signal(self):
        payload = "BJ:STAND___"
        self._send_with_ack_logic(payload)
        print(f"Sending: {payload}")

    def send_ready_status(self, is_ready):
        if is_ready:
            payload = "BJ:RDY_____"
            self._send_with_ack_logic(payload)
            print(f"Sending: {payload}")
        else:
            payload = "BJ:NRD_____"
            self._send_with_ack_logic(payload)
            print(f"Sending: {payload}")
    
    def send_bet_amount(self, amount):
        payload = f"BJ:BT______:{amount}"
        self._send_with_ack_logic(payload)
        print(f"Sending: {payload}")
    
    def send_gamestate_request(self):
        payload = "BJ:REC__GAM"
        self.send_fire_and_forget(payload)
        print(f"Sending: {payload}")

    def send_fire_and_forget(self, payload): 
        if self.network:
            self.network.send_message(payload)

    def _send_with_ack_logic(self, payload): 
        self.pending_msg = payload
        self.retry_count = 0
        self.waiting_for_ack = True
        self.last_send_time = time.time()
        
        if self.network:
            self.network.send_message(payload)

    

    def on_network_message(self, raw_msg):
        # 1. Validate Protocol
        if not raw_msg.startswith("BJ:"):
            self.invalid_msg_count += 1
            print(f"DEBUG: Discarding invalid protocol message: {raw_msg}")
            if self.invalid_msg_count > 3:
                print("DEBUG: Too many invalid messages, disconnecting...")
                self._notify_gui("close_cli", "Detected invalid messages from server")
                if self.network:
                    self.network._running = False
            return

        self.last_message_time = time.time()

        #  Process Valid Message
        content = raw_msg[3:].strip() # Remove "BJ:"

        cmd, args = (content.split(":", 1) + [None])[:2]

        if cmd.split("_")[0] == "ACK" and self.waiting_for_ack:
            self.waiting_for_ack = False
            self.pending_msg = None
            self._notify_gui(cmd, args)
        elif cmd.split("_")[0] == "NACK" and self.waiting_for_ack:
            self.waiting_for_ack = False
            self.pending_msg = None
            self._notify_gui(cmd, args)
        elif cmd == "PING____":
            self.reconnect_atmpt = 0
            pong_msg = "BJ:PONG____"
            if self.network:
                self.network.send_message(pong_msg)
        elif cmd == "mark_offline":
            self.invalid_msg_count += 1
            self.connected = False
        else:
            self._notify_gui(cmd , args)

    def on_tick(self):
        if self.reconnect_atmpt > 5:
            self._notify_gui("close_cli","Ran out of reconnection attempts.")

        if self.last_message_time > 0 and (time.time() - self.last_message_time) > 10: ## and self.connected) was removed because it prevented repetitive reconnection attempts
            print("DEBUG: Connection timeout detected, marking for reconnection...")
            self._notify_gui("mark_offline", None)
            # Don't reconnect directly from the network thread - signal it to stop instead
            self.network._running = False
            self.last_message_time = time.time() 
            self.connected = False
            self.reconnect_atmpt+=1
            return
            

        """Called periodically by the Network Loop to handle timeouts."""
        if self.waiting_for_ack and self.pending_msg:
            now = time.time()
            if (now - self.last_send_time) > self.TIMEOUT_SEC:
                if self.retry_count < self.MAX_RETRIES:
                    self.retry_count += 1
                    self.last_send_time = now
                    print(f"DEBUG: Timeout. Resending ({self.retry_count}/{self.MAX_RETRIES})...")
                    print(f"Timeout. Retry {self.retry_count}...")
                    
                    if self.network:
                        self.network.send_message(self.pending_msg)
                else:
                    self.waiting_for_ack = False
                    self.pending_msg = None
                    print("FAILURE: Max retries reached. No ACK.")

    def _notify_gui(self, cmd, args):
        """Puts a message onto the GUI-safe queue."""
        self.gui_queue.put((cmd, args))

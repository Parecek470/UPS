"""BlackJack Client Application - GUI Layer"""
"""author: Marek Manzel"""
""" responsibilities: Tkinter GUI, user interaction, display updates """
import sys
import os
import queue
import tkinter as tk
import argparse
import ipaddress
from tkinter import messagebox
from enum import Enum
from PIL import Image, ImageTk

from network import NetworkClient
from dataman import ProtocolController


#game state enum
class GameState(Enum):
    WAITING = 0
    BETTING = 1
    PLAYING = 2
    ROUND_END = 3

GameState = Enum('GameState', [('Waiting for players', 0), ('Betting phase', 1), ('Playing', 2), ('Evaluating results', 3)])

class BlackJackGui:
    def __init__(self, root, host, port):
        self.root = root
        self.root.title(f"BlackJack Client - {host}:{port}")
        self.root.geometry("800x600")

        # GAMESTATES

        # player info
        self.isready = False

        # Config
        self.host = host
        self.port = port
        
        # Safe Queue for cross-thread communication (Protocol -> GUI)
        self.gui_event_queue = queue.Queue()

        # Initialize data Layers
        self.protocol = ProtocolController(self.gui_event_queue)
        self.network = NetworkClient(
            self.host, 
            self.port, 
            incoming_callback=self.protocol.on_network_message,
            tick_callback=self.protocol.on_tick
        )
        self.protocol.set_network(self.network)
        self.protocol.connected = True

        self.root.resizable(False, False)
        
        self.container = tk.Frame(self.root)
        self.container.pack(fill="both", expand=True)
        
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        self.frames = {}
        

        #_______________Player Info_________________
        self.player_info = PlayerInfo(self.root)
        self.player_info.place(x=600, y=5) # Top-right corner

        # Disconnection modal reference
        self.disconnection_modal = None

        for F in (Lobby, GameRoom):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")
            
        self.show_frame("Lobby")

        # modal for nickname input
        self.login_modal = None

        self._start_network()
        # Start GUI Queue Consumer
        self.root.after(100, self._process_gui_queue)
        # connection monitoring
        self.root.after(2000, self._monitor_connection)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_app)

    def show_warning(self, title, message, parent=None):
        """Show a warning messagebox that appears in front."""
        target = parent or self.root
        target.attributes('-topmost', True)
        target.focus_force()
        target.update()
        messagebox.showwarning(title, message, parent=target)
        target.attributes('-topmost', False)

    def show_askokcancel(self, title, message, parent=None):
        """Show an askokcancel dialog that appears in front."""
        target = parent or self.root
        target.attributes('-topmost', True)
        target.focus_force()
        target.update()
        result = messagebox.askokcancel(title, message, parent=target)
        target.attributes('-topmost', False)
        return result

    def open_login_modal(self):
        #create a modal dialog for nickname input, blocking user interaction with main window
        if self.login_modal:
            return # Already open

        if self.player_info.raw_nick != "" and self.player_info.raw_nick is not None:
            self.protocol.send_nickname_request(self.player_info.raw_nick)
            return

        self.login_modal = tk.Toplevel(self.root)
        self.login_modal.title("Login")
        self.login_modal.geometry("300x150")
        self.login_modal.resizable(False, False)
        
        # Modal behavior: Keep on top and disable main window
        self.login_modal.transient(self.root) 
        self.login_modal.grab_set() 
        
        # Center the modal
        x = self.root.winfo_x() + (800 // 2) - (300 // 2)
        y = self.root.winfo_y() + (600 // 2) - (150 // 2)
        self.login_modal.geometry(f"+{x}+{y}")

        # UI Elements
        tk.Label(self.login_modal, text="Enter Nickname:", font=("Arial", 12)).pack(pady=10)
        
        self.validnickname = (self.root.register(self._validate_nickname), '%P')
        self.ent_nick = tk.Entry(self.login_modal, font=("Arial", 12), validate="key", validatecommand=self.validnickname)
        self.ent_nick.pack(pady=5)
        self.ent_nick.focus_set() # Focus the cursor here
        self.login_modal.attributes('-topmost', True)

        # Bind Enter key to submit
        self.ent_nick.bind("<Return>", lambda e: self._on_login_click())

        tk.Button(self.login_modal, text="Login", bg="#4CAF50", fg="white", 
                  command=self._on_login_click).pack(pady=10)
        
        # Prevent closing via 'X' button (optional, forces user to login)
        self.login_modal.protocol("WM_DELETE_WINDOW", self._on_close_app)

    def _validate_nickname(self, newValue: str):
        """Validate nickname: max 10 chars, alphanumeric only. "-" , "_" allowed."""
        if newValue == "":
            return True
        if len(newValue) <= 10 and all(c.isalnum() or c in "-_" for c in newValue):
            return True
        return False

    def _on_login_click(self):
        nick = self.ent_nick.get().strip()
        if not nick or len(nick) < 3 or len(nick) > 10:
            self.show_warning("Input", "Nickname must be between 3 and 10 characters.", self.login_modal)
            return
        elif ";" in nick or ":" in nick:
            self.show_warning("Input", "Nickname cannot contain ';' or ':'.", self.login_modal)
            return

        self.protocol.send_nickname_request(nick)

    def _on_close_app(self, force=False):
        """Clean shutdown: destroys modal, root, and exits."""
        if force or self.show_askokcancel("Quit", "Do you want to quit?"):
            # 1. Close connection if it exists
            if hasattr(self, 'network'):
                self.network._close_connection("user exit") 
            
            # 2. Destroy the GUI
            self.root.destroy()
            sys.exit(0)


    def show_frame(self, page_name, room_number=None):
        frame = self.frames[page_name]
        frame.tkraise()
        
        # FIX: Force the UI to update its calculations immediately
        frame.update_idletasks()
        
        # If switching to GameRoom, we manually trigger the drawing
        # to ensure it appears even if the resize event didn't fire.
        #if page_name == "GameRoom":
            #frame.draw_oval()
            #if room_number is not None:
                #frame.open_modal(room_number)

    

    def _start_network(self):
        success, msg = self.network.start()
        if success:
            print(f"System: {msg}")
        else:
            print(f"System Error: {msg}")

   

    def _process_gui_queue(self):
        """
        Periodically checks the queue for messages from the Protocol Layer.
        This keeps the GUI responsive while receiving data from background threads.
        """
        try:
            while True:
                # Non-blocking pop
                cmd, args = self.gui_event_queue.get_nowait()
                self.process_gui_message(cmd, args)
        except queue.Empty:
            pass
        finally:
            # Reschedule check
            self.root.after(100, self._process_gui_queue)

    def _monitor_connection(self):
        """Periodically check network connection status."""
        self._check_connection_status()
        self.root.after(2000, self._monitor_connection)
        
    def _check_connection_status(self):
        """Check if network thread has died and attempt reconnection if needed."""
        if hasattr(self, 'network') and self.network:
            # Check if network thread is still running
            if not self.network._running and self.network._thread:
                # Only reconnect if thread has actually stopped
                if not self.network._thread.is_alive():
                    self.process_gui_message("mark_offline", None)  # Notify GUI of disconnection
                    print("DEBUG: Network thread stopped, attempting reconnection...")
                    
                    # Create new network connection
                    new_network = NetworkClient(
                        host=self.host,
                        port=self.port,
                        incoming_callback=self.protocol.on_network_message,
                        tick_callback=self.protocol.on_tick
                    )
                    
                    success, msg = new_network.start()
                    if success:
                        self.protocol.set_network(new_network)
                        self.network = new_network  # Update our reference
                        print("DEBUG: Reconnection attempt...")
                    else:
                        print(f"DEBUG: Reconnection failed: {msg}")

    def show_disconnection_modal(self):
        """Show disconnection modal with blocking interaction."""
        if self.disconnection_modal:
            return  # Already open
        

        self.disconnection_modal = tk.Toplevel(self.root)
        self.disconnection_modal.title("Connection Lost")
        
        # 1. Start Hidden (Prevents the "Flash")
        self.disconnection_modal.withdraw()

        # 2. Configure Window
        window_size = 400
        self.disconnection_modal.geometry(f"{window_size}x{window_size}")
        self.disconnection_modal.resizable(False, False)
        self.disconnection_modal.transient(self.root)
        self.disconnection_modal.grab_set()

        # Define styles
        text_bg = "#E1EFFD"
        text_color = "black"

        # Load and display disconnected image (Background)
        try:
            if os.path.exists("disconnected.jpg"):
                img = Image.open("disconnected.jpg")
                
                # 2. Resize to fill the modal completely (400x400)
                img = img.resize((window_size, window_size), Image.Resampling.LANCZOS)
                self.disconnection_image = ImageTk.PhotoImage(img)
                
                # Use Place to make it a background
                img_label = tk.Label(self.disconnection_modal, image=self.disconnection_image)
                img_label.place(x=0, y=0, relwidth=1, relheight=1)
            else:
                # Fallback background if image missing
                self.disconnection_modal.configure(bg=text_bg)
                tk.Label(self.disconnection_modal, text="Connection Lost", 
                         font=("Arial", 16, "bold"), fg="red", bg=text_bg).pack(pady=20)
        except Exception as e:
            print(f"Error loading disconnected.jpg: {e}")
            self.disconnection_modal.configure(bg=text_bg)

        # 3. Text and Buttons (Placed on top of image)
        # Note: Using .place() instead of .pack() to layer over the image
        
        # Status message
        tk.Label(self.disconnection_modal, text="It appears you have no connection.", 
                 font=("Arial", 14, "bold"), fg=text_color, bg=text_bg).place(relx=0.5, rely=0.9, anchor="center")
        
        tk.Label(self.disconnection_modal, text="Attempting to reconnect...", 
                 font=("Arial", 10), fg=text_color, bg=text_bg).place(relx=0.5, rely=0.95, anchor="center")
        

        self.root.update_idletasks()
        self.disconnection_modal.update_idletasks()

        # 4. Calculate Center Relative to Main Window
        # Get Main Window dimensions and position
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()

        # Calculate offsets
        x = root_x + (root_w // 2) - (window_size // 2)
        y = root_y + (root_h // 2) - (window_size // 2)

        # Apply Geometry
        self.disconnection_modal.geometry(f"+{x}+{y}")
        
        # 5. Reveal
        self.disconnection_modal.deiconify()
        self.disconnection_modal.attributes('-topmost', True)
        self.disconnection_modal.protocol("WM_DELETE_WINDOW", self._on_close_app)


    def hide_disconnection_modal(self):
        """Hide disconnection modal when reconnected."""
        if self.disconnection_modal:
            self.disconnection_modal.destroy()
            self.disconnection_modal = None

    def process_gui_message(self, cmd, args):
        """Thread-safe update of text widget."""
        print(f"Command: {cmd}, Args: {args}")
        if cmd == "REQ_NICK":
            self.player_info.update_data(status="Online")
            self.hide_disconnection_modal()  # Hide disconnection modal when back online
            self.open_login_modal()
        elif cmd == "ACK__NIC":
            if self.login_modal:
                self.login_modal.destroy()
                self.login_modal = None
            self.hide_disconnection_modal()  # Hide disconnection modal when back online
            self.show_frame("Lobby")
            self.player_info.update_data(nickname=args.split(";")[0], credits=args.split(";")[1], status="Online")
            self.frames["Lobby"].show_loading()
        elif cmd == "ACK__REC":
            if self.login_modal:
                self.login_modal.destroy()
                self.login_modal = None
            self.hide_disconnection_modal()  # Hide disconnection modal when back online
            if args.split(";")[-1] == "-1":
                self.handle_leave_room()
                self.show_frame("Lobby")
                self.player_info.update_data(nickname=args.split(";")[0], credits=args.split(";")[1], status="Online")
                self.frames["Lobby"].show_loading()
            else:
                self.player_info.update_data(nickname=args.split(";")[0], credits=args.split(";")[1], status="Online")
                self.show_frame("GameRoom")
                self.protocol.send_gamestate_request()
        elif cmd == "NACK_NIC":
            self.show_warning("Login Failed", f"Nickname rejected: {args}")
        elif cmd == "ACK__JON":
            self.handle_join_room(args)
        elif cmd == "NACK_JON":
            self.show_warning("Join Room Failed", f"Failed to join room: {'Not enough credits' if self.player_info.raw_credits == 0 else args}")
        elif cmd == "LBBYINFO":
            # update players online 
            online_count, room_count, room_data = args.split(":", 2)
            self.frames["Lobby"].update_room_list(room_data)
        elif cmd == "REQ_BET_":
            # open betting modal
            self.frames["GameRoom"].ready_modal.destroy()
            self.frames["GameRoom"].ready_modal = None
            self.frames["GameRoom"].open_bet_modal()
        elif cmd == "ACK___BT":
            self.frames["GameRoom"].bet_modal.destroy()
            self.frames["GameRoom"].bet_modal = None
            self.player_info.update_data(credits=self.player_info.raw_credits - int(args))
            self.frames["GameRoom"].show_waiting()
        elif cmd == "NACK__BT":
            self.show_warning("Bet Failed", f"Failed to place bet: {args}")
        elif cmd == "GAMESTAT":
            self.frames["GameRoom"].hide_waiting()
            self.frames["GameRoom"].update_game_state(args)
        elif cmd == "ROMSTAUP":
            # room status update
            if self.frames["GameRoom"].ready_modal is not None:
                self.frames["GameRoom"]._update_players_list(args)
            elif self.frames["GameRoom"].placed_bet and self.frames["GameRoom"].waiting_for_cards:
                self.frames["GameRoom"]._update_players_card(args)
            elif not self.frames["GameRoom"].player_ready_status and self.frames["GameRoom"].ready_modal is None:
                self.frames["GameRoom"].open_ready_modal()
                self.frames["GameRoom"]._update_players_list(args)
            else:
                print("ROMSTAUP: No action taken.")
        elif cmd == "ACK_LVRO":
            self.handle_leave_room()
            self.show_frame("Lobby")
        elif cmd == "ROUNDEND":
            self.frames["GameRoom"].update_game_end(args)
        elif cmd == "ACK__PAG":
            self.handle_leave_room()
            self.handle_join_room(args)
        elif cmd == "NACK_PAG":
            self.handle_leave_room()
            self.show_frame("Lobby")
            self.show_warning("Play Again Failed", f"Failed to play again: {args}")
        elif cmd == "CON_FAIL":
            self.show_warning("Connection Failed", f"Failed to connect to server: {args}")
            self._on_close_app(force=True)
        elif cmd == "mark_offline":
            self.show_disconnection_modal()  # Show disconnection modal
            self.player_info.update_data(status="Offline")
            if "GameRoom" in self.frames and self.player_info.raw_nick in self.frames["GameRoom"].player_cards:
                self.frames["GameRoom"].player_cards[self.player_info.raw_nick].update_data(status="Disconnected")
            
            
            
    def handle_join_room(self, room_num):
        old_room = self.frames["GameRoom"]
        old_room.destroy()
        new_room = GameRoom(parent=self.container, controller=self)
        self.frames["GameRoom"] = new_room
        new_room.grid(row=0, column=0, sticky="nsew")
        self.frames["Lobby"].join_room(room_num)

    def handle_leave_room(self):
        tm = self.frames["GameRoom"].ready_modal
        if tm:
            tm.destroy()
            self.frames["GameRoom"].ready_modal = None
        bm = self.frames["GameRoom"].bet_modal
        if bm:
            bm.destroy()
            self.frames["GameRoom"].bet_modal = None
        em = self.frames["GameRoom"].game_end_modal
        if em:
            em.destroy()
            self.frames["GameRoom"].game_end_modal = None


class PlayerInfo(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg="#333", highlightbackground="#555", highlightthickness=2)

        # --- NEW: Store raw data variables ---
        self.raw_nick = ""
        self.raw_credits = 0
        self.raw_status = "Offline"

        # Labels (Display)
        self.lbl_nick = tk.Label(self, text=f"Nick: {"???" if not self.raw_nick else self.raw_nick}", bg="#333", fg="white", font=("Arial", 10, "bold"))
        self.lbl_credits = tk.Label(self, text=f"Credits: {self.raw_credits}", bg="#333", fg="#FFD700", font=("Arial", 10))
        self.lbl_status = tk.Label(self, text=f"Status: {self.raw_status}", bg="#333", fg="#aaa", font=("Arial", 10, "italic"))

        # Layout
        self.lbl_nick.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        self.lbl_credits.grid(row=1, column=0, sticky="w", padx=5)
        self.lbl_status.grid(row=2, column=0, sticky="w", padx=5, pady=(0, 5))

    def update_data(self, nickname=None, credits=None, status=None):
        """Updates both the raw data and the UI labels."""
        if nickname is not None:
            self.raw_nick = nickname
            self.lbl_nick.config(text=f"Nick: {nickname}")
            
        if credits is not None:
            self.raw_credits = int(credits) # Ensure it's a number
            self.lbl_credits.config(text=f"Credits: {self.raw_credits}")
            
        if status is not None:
            self.raw_status = status
            self.lbl_status.config(text=f"Status: {status}")

class Lobby(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="#f0f0f0")

        header = tk.Label(self, text="Lobby - Choose a Room", font=("Arial", 24), bg="#f0f0f0")
        header.pack(pady=10, fill="x")

        container_frame = tk.Frame(self, bg="#f0f0f0")
        container_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(container_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = tk.Scrollbar(container_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#f0f0f0")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.room_widgets = {}

        self.loading_label = tk.Label(self, text="Loading Rooms...", bg="#90EE90", fg="#006400",
                                      font=("Arial", 14, "bold"), relief="raised", borderwidth=2)
        
        
        
    def show_loading(self):
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center", width=200, height=50)
        self.loading_label.tkraise()

    def hide_loading(self):
        self.loading_label.place_forget()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def create_room_card(self, room_id, room_data):
        card = tk.Canvas(self.scrollable_frame, width=200, height=150, bg="white", highlightthickness=0)

        card.create_rectangle(2, 2, 198, 148, outline="#ccc", width=1)

        card.text_id = card.create_text(100, 25, text=f"Room {room_id+1}", font=("Arial", 16, "bold"))

        players, state = room_data.split(";")

        card.players_id = card.create_text(100, 55, text=f"Players: {players}", font=("Arial", 12))
        card.state_id = card.create_text(100, 80, text=f"State: {GameState(int(state)).name}", font=("Arial", 12))

        join_btn = tk.Button(card, text="JOIN", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
                             command=lambda: self.join_room_request(room_id))
        card.create_window(100, 120, window=join_btn)

        return card


    def update_room_list(self, room_string):
        # room string format: R0;0/7;0:R1;0/7;0:R2;0/7;0:R3;0/7;0:R4;0/7;0:R5;0/7;0: 
        # R0 = room id
        # 0/7 = players
        # 0 = GameState enum value
        self.hide_loading()
        raw_items = [x for x in room_string.split(":") if x]

        incoming_data = {}
        for item in raw_items:
            rid, data_str = item.split(";", 1)
            rid = int(rid[1:])  
            incoming_data[rid] = data_str

        existing_ids = set(self.room_widgets.keys())
        incoming_ids = set(incoming_data.keys())

        for rid in existing_ids - incoming_ids: #remove missing rooms, in current server state should never happen
            self.room_widgets[rid].destroy()
            del self.room_widgets[rid]

        for rid, data in incoming_data.items(): #create or update rooms
            if rid not in self.room_widgets:
                new_card = self.create_room_card(rid, data)
                self.room_widgets[rid] = new_card
            else:
                widget = self.room_widgets[rid]
                players, state = data.split(";")

                widget.itemconfig(widget.players_id, text=f"Players: {players}")
                state_name = GameState(int(state)).name
                widget.itemconfig(widget.state_id, text=f"State: {state_name}")

        sorted_ids = sorted(self.room_widgets.keys())
        columns_per_row = 3
        for index, rid in enumerate(sorted_ids):
            row = index // columns_per_row
            col = index % columns_per_row
            card = self.room_widgets[rid]
            card.grid(row=row, column=col, padx=15, pady=15)

        self.scrollable_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def join_room_request(self, room_num):
        # Hand off to Protocol Layer - Non-blocking
        self.controller.protocol.send_join_room_request(room_num)
    
    def join_room(self, room_num):
        self.controller.show_frame("GameRoom", room_num)

class GameRoom(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="white")
        
        # 1. Back button (Takes up roughly 50px height with padding)
        back_btn = tk.Button(self, text="< Back to Lobby", command=lambda: self.leave_room(), bg="#f58a83", fg="white", font=("Arial", 12, "bold"))
        back_btn.pack(anchor="nw", padx=10, pady=10)
        
        # 2. Canvas fills the rest
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.bind("<Configure>", self.draw_table)
        self.ready_modal = None
        self.bet_modal = None
        self.game_end_modal = None

        self.waiting_for_cards = True
        self.player_ready_status = False
        self.placed_bet = False
        

        self.waiting_label = tk.Label(self, text="Wait for others.", width=400,bg="#90EE90", fg="#006400",
                                      font=("Arial", 14, "bold"), relief="raised", borderwidth=2)
        
        # container for playercards
        self.player_cards = {}

        #dealer cards
        self.dealer_canvas = tk.Canvas(self, width=300, height=120, bg="#228B22", highlightthickness=0)
        self.dealer_canvas.pack(pady=20)

        self.hit_btn = tk.Button(self, text="HIT", state="disabled", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                                    command=self._on_hit_click)
        self.hit_btn.place(relx=0.4, rely=0.9, anchor="center")

        self.stand_btn = tk.Button(self, text="STAND", state="disabled", bg="#f49b36", fg="white", font=("Arial", 12, "bold"),
                                    command=self._on_stand_click)
        self.stand_btn.place(relx=0.6, rely=0.9, anchor="center")

    def _on_hit_click(self):
        self.controller.protocol.send_hit_signal()

    def _on_stand_click(self):
        self.controller.protocol.send_stand_signal()

    def show_waiting(self):
        self.waiting_label.place(relx=0.5, rely=0.5, anchor="center", width=200, height=50)
        self.waiting_label.tkraise()

    def hide_waiting(self):
        # Hide the waiting label if not already hidden
        if self.waiting_label:
            self.waiting_label.place_forget()

    def draw_table(self, event=None):
        self.canvas.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()

        # Simple responsive scaling
        x1, y1 = w * 0.1, h * 0.1
        x2, y2 = w * 0.9, h * 0.6# Leave bottom 30% for player cards

        # Draw Green Table
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#228B22", outline="#006400", width=4)

        # Place Dealer Canvas near top center of the green felt
        self.dealer_canvas.config(bg="#228B22")
        self.dealer_canvas.place(relx=0.5, rely=0.30, anchor="center")

        self._reposition_player_cards()

    def _reposition_player_cards(self):
        """Calculates positions to place player cards evenly at the bottom."""
        players = list(self.player_cards.values())
        count = len(players)
        if count == 0:
            return

        w = self.winfo_width()
        h = self.winfo_height()
        
        # Area for cards: Bottom 20% of screen
        card_area_y = h * 0.7
        
        # Spacing logic: divide width into (count + 1) segments
        segment_width = w / (count + 1)
        
        for i, card_widget in enumerate(players):
            x_pos = segment_width * (i + 1)
            # Center the widget at calculated X, fixed Y
            card_widget.place(x=x_pos, y=card_area_y, anchor="center", width=100, height=160)
            card_widget.tkraise()

    def _update_players_card(self, gameroom_data):
        """
        Parses ROMSTAUP. 
        Format Example: P;John;0;BET;10:P;carl;1;BET;55:
        """
        # disable buttons until game starts
        self.hit_btn.pack_forget()
        self.stand_btn.pack_forget()

        raw_players = [p for p in gameroom_data.split(":") if p]
        
        # Track current nicks to handle disconnects (optional cleanup)
        current_nicks = set()

        for player_str in raw_players:
            # Expected parts: [Type, Nick, ReadyStatus, BetKeyword, BetAmount]
            # e.g. ['P', 'John', '0', 'BET', '10']
            parts = player_str.split(";")
            
            if len(parts) >= 2 and parts[0] == 'P':
                nick = parts[1]
                status = parts[2]
                current_nicks.add(nick)
                
                # Check for Bet data (variable length support)
                bet_val = 0
                if len(parts) >= 5 and parts[3] == "BET":
                    bet_val = parts[4]

                # --- B. Update Table Widgets ---
                if nick not in self.player_cards:
                    # Create new card widget
                    pc = PlayerCard(self)
                    self.player_cards[nick] = pc
                    # Trigger a layout update
                    self._reposition_player_cards()
                
                # Update widget data
                self.player_cards[nick].update_data(
                    nickname=nick,
                    bet=bet_val,
                    status="Waiting"
                )
                if nick == self.controller.player_info.raw_nick:
                    self.player_ready_status = (status == '1')

    def update_game_state(self, state_str):
        """
        Parses GAMESTAT.
        Format Example: D;JS;6D:P;John;1;3D;5C:P;carl;0;3D;5C:
        """
        print(f"Game State Update: {state_str}")
        
        items = [x for x in state_str.split(":") if x]
        
        for item in items:
            parts = item.split(";")
            msg_type = parts[0] # 'D' or 'P'
            
            if msg_type == 'D':
                # Dealer: D;Card1;Card2...
                cards = parts[1:]
                
                # --- DRAW DEALER CARDS ---
                self.dealer_canvas.delete("all") # Clear previous
                
                # Draw "Dealer" text label on the canvas itself
                self.dealer_canvas.create_text(150, 15, text="DEALER", fill="white", font=("Arial", 12, "bold"))

                # Logic to center/fan dealer cards
                card_w, card_h = 60, 84  # Smaller cards for dealer? Or same size.
                total_w = len(cards) * (card_w + 5)
                start_x = (300 - total_w) / 2
                start_y = 30 # Below the text
                
                for i, card_code in enumerate(cards):
                    draw_vector_card(
                        self.dealer_canvas, 
                        start_x + (i * (card_w + 5)), 
                        start_y, 
                        card_w, card_h, 
                        card_code
                    )
                
            elif msg_type == 'P':
                # Player: P;Nick;Card1;Card2...
                if len(parts) >= 2:
                    nick = parts[1]
                    state = parts[2]
                    cards = parts[3:] # List of cards
                    
                    match state:
                        case '0':
                            tmp = "Standing"
                        case '1':
                            tmp = "Playing"
                        case '2':
                            tmp = "Disconnected"


                    if nick in self.player_cards:
                        self.player_cards[nick].update_data(cards=cards, status=tmp)
                    else:
                        # Should not happen usually, but create if missing
                        pc = PlayerCard(self)
                        self.player_cards[nick] = pc
                        pc.update_data(nickname=nick, cards=cards, status=tmp)
                        self._reposition_player_cards()
                    if nick == self.controller.player_info.raw_nick:
                        self.player_cards[nick].update_data(cards=cards, status=(tmp if self.controller.player_info.raw_status != "Offline" else "Disconnected"))
                        if state == '1':
                            self.hit_btn.config(state=tk.NORMAL, bg="#4CAF50", cursor="hand2")
                            self.stand_btn.config(state=tk.NORMAL, bg="#f49b36", cursor="hand2")
                        else:
                            self.hit_btn.config(state=tk.DISABLED, bg="#cccccc", cursor="")
                            self.stand_btn.config(state=tk.DISABLED, bg="#cccccc", cursor="")

    def open_ready_modal(self):
        if self.ready_modal:
            return # Already open

        self.ready_modal = tk.Toplevel(self.controller.root)
        self.ready_modal.title("Ready Up")
        self.ready_modal.geometry("450x300")
        self.ready_modal.resizable(False, False)

        # Modal behavior: Keep on top and disable main window
        self.ready_modal.transient(self.controller.root)
        self.ready_modal.grab_set()

        # Center the modal
        x = self.controller.root.winfo_x() + (800 // 2) - (300 // 2)
        y = self.controller.root.winfo_y() + (600 // 2) - (150 // 2)
        self.ready_modal.geometry(f"+{x}+{y}")

        # UI Elements
        tk.Label(self.ready_modal, text="Waiting for players: ", font=("Arial", 12)).pack(pady=10)

        #list of players which will be updated dynamically
        self.players_listbox = tk.Listbox(self.ready_modal, font=("Arial", 12), width=40, height=10)
        self.players_listbox.pack(pady=5)
        
        self.leavebutton = tk.Button(self.ready_modal, text="Leave Room", bg="#f44336", fg="white",
                  command=lambda: self.leave_room())
        self.leavebutton.place(x=10, y=260)

        self.readybutton = tk.Button(self.ready_modal, text="READY", bg="#4CAF50", fg="white",
                  command=lambda: self._on_ready_click(not self.player_ready_status))
        self.readybutton.place(x=370, y=260)

        #disable closing the modal to force ready
        self.ready_modal.protocol("WM_DELETE_WINDOW", lambda: self.leave_room())

    def leave_room(self):
        self.controller.protocol.send_leave_room_request()

    def open_bet_modal(self):
        #create a modal dialog for betting
        if self.bet_modal:
            return # Already open

        self.bet_modal = tk.Toplevel(self.controller.root)
        self.bet_modal.title("Place Your Bet")
        self.bet_modal.geometry("450x200")
        self.bet_modal.resizable(False, False)

        # Modal behavior: Keep on top and disable main window
        self.bet_modal.transient(self.controller.root)
        self.bet_modal.grab_set()
        
        # Center the modal
        x = self.controller.root.winfo_x() + (800 // 2) - (225 // 2)  # 450/2 = 225
        y = self.controller.root.winfo_y() + (600 // 2) - (100 // 2)  # 200/2 = 100
        self.bet_modal.geometry(f"450x200+{x}+{y}")

        # Make window visible first
        self.bet_modal.deiconify()
        self.bet_modal.update_idletasks()
        
        # NOW remove decorations to make it borderless
        self.bet_modal.overrideredirect(True)
        
        # Re-apply positioning after removing decorations
        self.bet_modal.geometry(f"450x200+{x}+{y}")
        
        # Ensure it stays on top
        self.bet_modal.attributes('-topmost', True)

        # UI Elements
        tk.Label(self.bet_modal, text="Place your bet: ", font=("Arial", 12)).pack(pady=10)
        self.errwarning_label = tk.Label(self.bet_modal, text="", font=("Arial", 10), fg="red")
        self.errwarning_label.pack(pady=5)

        # Entry for bet amount
        self.bet_amount_entry = tk.Entry(self.bet_modal, font=("Arial", 12))
        self.bet_amount_entry.pack(pady=5)

        # Bind Enter key to submit
        self.bet_amount_entry.bind("<Return>", lambda e: self._on_place_bet())

        tk.Button(self.bet_modal, text="PLACE BET", bg="#4CAF50", fg="white",
                  command=self._on_place_bet).pack(pady=10)
        
        # Force focus after everything is set up - use multiple methods for reliability
        self.bet_modal.lift()
        self.bet_modal.focus_force()
        
        # Set focus to entry with a delay to ensure window is fully ready
        def set_focus():
            try:
                self.bet_amount_entry.focus_set()
                self.bet_amount_entry.icursor(tk.END)  # Position cursor at end
            except:
                pass

        def force_focus(event):
            self.controller.root.focus_force()
            self.bet_amount_entry.focus_force()

        self.bet_modal.bind("<Button-1>", force_focus)  # Also set focus on click
        self.bet_amount_entry.bind("<Button-1>", force_focus)
    
        self.bet_modal.after(100, set_focus)  # Slightly longer delay for borderless windows
    
    def open_game_end_modal(self):
        #create a modal dialog for game end
        if self.game_end_modal:
            return # Already open

        self.game_end_modal = tk.Toplevel(self.controller.root)
        self.game_end_modal.title("Game Over")
        self.game_end_modal.geometry("450x300")
        self.game_end_modal.resizable(False, False)

        # Modal behavior: Keep on top and disable main window
        self.game_end_modal.transient(self.controller.root)
        self.game_end_modal.grab_set()

        # Center the modal
        x = self.controller.root.winfo_x() + (800 // 2) - (300 // 2)
        y = self.controller.root.winfo_y() + (600 // 2) - (150 // 2)
        self.game_end_modal.geometry(f"+{x}+{y}")

        # UI Elements
        tk.Label(self.game_end_modal, text="Game Finished", font=("Arial", 12)).pack(pady=10)

        self.game_end_credits = tk.Label(self.game_end_modal, text="Credits: ", font=("Arial", 12))
        self.game_end_credits.pack(pady=5)

        self.game_end_winnings = tk.Label(self.game_end_modal, text="Winnings: ", font=("Arial", 12))
        self.game_end_winnings.pack(pady=5)

        tk.Button(self.game_end_modal, text="Leave Room", bg="#f44336", fg="white",
                  command=lambda: self.leave_room()).pack(pady=10)

        tk.Button(self.game_end_modal, text="Play again", bg="#4CAF50", fg="white",
                  command=self._on_play_again).pack(pady=10)

    def _on_play_again(self):
        #send ready message to server
        self.controller.protocol.send_play_again_signal()
        print("Play again clicked")

    def update_game_end(self, result_str):
        if not self.game_end_modal:
            self.open_game_end_modal()
        credits,winnings = result_str.split(";")
        self.game_end_credits.config(text=f"Credits: {credits}")
        self.game_end_winnings.config(text=(f"Winnings: {winnings}" if int(winnings) > 0 else f"Loss: {int(winnings)}"))
        self.controller.player_info.update_data(credits=credits)

    def _on_place_bet(self):
        bet_amount = self.bet_amount_entry.get()
        # Validate and process the bet amount
        if bet_amount.isdigit():
            self.controller.protocol.send_bet_amount(int(bet_amount))
        else:
            self.controller.show_warning("Invalid Bet", "Please enter a valid bet amount.")

    def _on_ready_click(self,isready):
        #send ready message to server
        self.controller.protocol.send_ready_status(isready)

    def _update_players_list(self, gameroom_players):
        self.players_listbox.delete(0, tk.END)
        for player in gameroom_players.split(":"):
            if not player:
                continue
            _,nick,status,__ = player.split(";", 3)
            if nick == self.controller.player_info.raw_nick:
                self.player_ready_status = (status == '1')
                #update button text
                if self.readybutton:
                    self.readybutton.config(text="READY" if not self.player_ready_status else "UNREADY")
            self.players_listbox.insert(tk.END, f"{nick} - {'Ready' if status=='1' else 'Not Ready'}")

    

class PlayerCard(tk.Frame):
    def __init__(self, parent, width=100, height=160):
        super().__init__(parent)
        self.target_w = width
        self.target_h = height
        
        # Height split: Top 45% for cards, Bottom 55% for Image/Info
        self.card_area_h = int(height * 0.45) 
        self.img_area_h = height - self.card_area_h

        # --- Load Status Images ---
        # We resize images to fit only the BOTTOM portion of the card
        image_map = {
            "disconnected": "bg_pl_disconnected.jpg",
            "playing":      "bg_pl_playing.jpg",
            "standing":     "bg_pl_waiting.jpg", # Reusing waiting for standing
            "waiting":      "bg_pl_waiting.jpg"
        }

        self.images = {} 
        for state_name, path in image_map.items():
            if os.path.exists(path):
                try:
                    raw_image = Image.open(path).convert("RGBA")
                    # Resize to fit width x (height - card_area)
                    raw_image = raw_image.resize((self.target_w, self.img_area_h), Image.Resampling.LANCZOS)
                    self.images[state_name] = ImageTk.PhotoImage(raw_image)
                except Exception as e:
                    print(f"Error loading {path}: {e}")
                    self.images[state_name] = None
            else:
                self.images[state_name] = None

        # --- Canvas Setup ---
        self.canvas = tk.Canvas(
            self, 
            width=self.target_w, 
            height=self.target_h, 
            bg="#2e2e2e", # Dark gray background for the card slot
            highlightthickness=0
        )
        self.canvas.pack()

        # --- State Variables ---
        self.raw_status = "waiting"
        self.raw_nick = "???"
        self.raw_bet = 0
        self.raw_cards = []

        # --- Initial Draw ---
        self._refresh_ui()

    def update_data(self, nickname=None, bet=None, status=None, cards=None):
        """Updates data and redraws the necessary parts."""
        needs_redraw = False
        
        if nickname is not None:
            self.raw_nick = nickname
            needs_redraw = True
            
        if bet is not None:
            self.raw_bet = int(bet)
            needs_redraw = True
            
        if status is not None and status.lower() != self.raw_status:
            self.raw_status = status.lower()
            needs_redraw = True

        if cards is not None:
            # Handle list or string input
            new_cards = cards.split(" ") if isinstance(cards, str) else cards
            # Filter out empty strings if any
            new_cards = [c for c in new_cards if c]
            if new_cards != self.raw_cards:
                self.raw_cards = new_cards
                needs_redraw = True

        if needs_redraw:
            self._refresh_ui()

    def _refresh_ui(self):
        """Clears and redraws the entire canvas."""
        self.canvas.delete("all")

        # 1. Draw Background Image (Bottom Section)
        img = self.images.get(self.raw_status)
        if img:
            self.canvas.create_image(0, self.card_area_h, image=img, anchor="nw")
        else:
            # Fallback rectangle if image missing
            self.canvas.create_rectangle(0, self.card_area_h, self.target_w, self.target_h, fill="#444")

        # 2. Draw Text Info (Overlaid on the image)
        # Nickname
        text_item = self.canvas.create_text(
            self.target_w/2, self.target_h - 10, 
            text=self.raw_nick, 
            fill="White", font=("Arial", 11, "bold"), anchor="center"
        )

        x1,y1,x2,y2 = self.canvas.bbox(text_item)

        bg_rect = self.canvas.create_rectangle(x1 - 4, y1 - 2, x2 + 4, y2 + 2, fill="Black", outline="")
        self.canvas.tag_lower(bg_rect, text_item)


        # Bet Amount
        if self.raw_bet > 0:
            self.canvas.create_text(
                self.target_w/2, self.target_h - 25, 
                text=f"${self.raw_bet}", 
                fill="#00FF2A", font=("Arial", 10, "bold"), anchor="center"
            )

        # 3. Draw Cards (Top Section)
        self._draw_cards_fan()

    def _draw_cards_fan(self):
        """Draws the list of cards in the top area, fanning them out."""
        if not self.raw_cards:
            # Draw a placeholder slot if no cards
            self.canvas.create_rectangle(
                20, 10, 20 + 40, 10 + 55, 
                outline="#555", dash=(2, 2)
            )
            return

        num_cards = len(self.raw_cards)
        
        # Dimensions for a single card
        card_w = 40
        card_h = 55
        start_y = 10
        
        # Calculate overlap to center them
        total_width_needed = (num_cards * card_w)
        overlap = 0
        
        # If cards don't fit, overlap them
        max_w = self.target_w - 10
        if total_width_needed > max_w:
            overlap = (total_width_needed - max_w) / (num_cards - 1)
        
        # Center the entire hand
        actual_width = (num_cards * card_w) - (overlap * (num_cards - 1))
        start_x = (self.target_w - actual_width) / 2

        for i, card_code in enumerate(self.raw_cards):
            x = start_x + (i * (card_w - overlap))
            self._draw_single_card(x, start_y, card_w, card_h, card_code)

    def _draw_single_card(self, x, y, w, h, code):
        """Draws a vector graphic playing card."""
        draw_vector_card(self.canvas, x, y, w, h, code)

def draw_vector_card(canvas, x, y, w, h, code):
    """
    Draws a single vector card on any Tkinter canvas.
    code: str, e.g., "10H", "AC", "6D", "XX" (back of card)
    """
    # 1. Background (White rect with border)
    # Tagging parts with 'card' allows easy deletion if needed, 
    # though usually we clear the whole canvas.
    canvas.create_rectangle(x, y, x+w, y+h, fill="white", outline="#888", width=1)

    # Handle "Hidden" card (e.g. Dealer's hole card)
    if code == "XX" or code == "??":
        # Draw a pattern for the back
        canvas.create_rectangle(x+2, y+2, x+w-2, y+h-2, fill="#b22222", outline="")
        canvas.create_line(x, y, x+w, y+h, fill="#a00000", width=2)
        canvas.create_line(x+w, y, x, y+h, fill="#a00000", width=2)
        return

    # Parse Code (e.g., "10H")
    if len(code) < 2: return
    
    suit_char = code[-1]       # Last char is suit
    value_char = code[:-1]     # Rest is value
    
    # Colors & Symbols
    if suit_char in ['H', 'D']:
        color = "#D40000" # Red
    else:
        color = "black"
        
    suits = {'H': '♥', 'D': '♦', 'C': '♣', 'S': '♠'}
    symbol = suits.get(suit_char, '?')

    # 2. Top-Left Corner Value
    font_size_val = max(8, int(h * 0.15)) # Dynamic font sizing
    canvas.create_text(x+4, y+5, text=value_char, fill=color, font=("Arial", font_size_val, "bold"), anchor="nw")
    
    # 3. Center Suit Symbol (Large)
    font_size_suit = int(h * 0.35)
    canvas.create_text(x+(w/2), y+(h/2), text=symbol, fill=color, font=("Arial", font_size_suit), anchor="center")
    
    # 4. (Optional) Bottom-Right Value (Rotated/Inverted is hard in Tkinter, so we just place it)
    canvas.create_text(x+w-4, y+h-5, text=value_char, fill=color, font=("Arial", font_size_val, "bold"), anchor="se")

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    # 1. Initialize the parser
    parser = argparse.ArgumentParser(description="Start the blackjack Client.")

    # 2. Define arguments
    # nargs='?' means the argument is optional.
    parser.add_argument("-i", "--ipaddress", default="127.0.0.1", 
                        help="The Server IP address (default: 127.0.0.1)")
    
    parser.add_argument("-p", "--port", type=int, default=10000, 
                        help="The Server Port (default: 10000)")

    # 3. Parse arguments
    args = parser.parse_args()

    # 4. specific logical validation (checking port range)
    if not (1 <= args.port <= 65535):
        print(f"Error: Port must be between 1 and 65535. Received: {args.port}")
        sys.exit(1)

    # chacking ip address validity
    try:
        ipaddress.ip_address(args.ipaddress)
    except ValueError:
        print(f"Error: Invalid IP address format: {args.ipaddress}")
        sys.exit(1)

    print(f"Configuration loaded: {args.ipaddress}:{args.port}")

    
    root = tk.Tk()

    # Note: We access the values via args.ipaddress and args.port
    app = BlackJackGui(root, args.ipaddress, args.port)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nClient shutting down...")
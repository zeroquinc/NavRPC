"""
System tray integration for NavRPC with status display and controls.
"""
import threading
import io
from pathlib import Path
from typing import Optional, Callable, Dict
from PIL import Image, ImageDraw
import pystray
from pystray import Menu, MenuItem

from .logger import get_logger

logger = get_logger()

class TrayIcon:
    """Manages the system tray icon and menu for NavRPC."""
    
    def __init__(self, on_exit: Optional[Callable] = None, on_restart: Optional[Callable] = None, on_reconnect: Optional[Callable] = None):
        """
        Initialize the system tray icon.
        
        Args:
            on_exit: Callback function to execute when Exit is selected
            on_restart: Callback function to execute when Restart is selected
            on_reconnect: Callback function to execute when Reconnect is selected
        """
        self.icon = None
        self.on_exit_callback = on_exit
        self.on_restart_callback = on_restart
        self.on_reconnect_callback = on_reconnect
        self.current_track: Optional[str] = None
        self.current_track_info: Optional[Dict[str, str]] = None
        self.album_art_url: Optional[str] = None
        self.album_art_data: Optional[bytes] = None  # Cache the actual image data
        self.is_running = False
        self._tray_thread: Optional[threading.Thread] = None

    def _get_icon_path(self) -> Optional[str]:
        """Return absolute path to the custom icon if it exists."""
        icon_path = (Path(__file__).resolve().parents[1] / "icon.ico")
        return str(icon_path) if icon_path.exists() else None
        
    def _create_icon_image(self) -> Image.Image:
        """Create or load the icon image for the system tray."""
        icon_path = self._get_icon_path()

        # Try to load custom icon first
        if icon_path:
            try:
                logger.info(f"Loading custom icon from {icon_path}")
                img = Image.open(icon_path)
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Resize to 64x64 if needed
                if img.size != (64, 64):
                    img = img.resize((64, 64), Image.Resampling.LANCZOS)
                return img
            except Exception as e:
                logger.warning(f"Could not load icon.ico: {e}, using default icon")
        
        # Fallback to generated icon
        logger.info("Using default generated icon")
        size = 64
        img = Image.new('RGB', (size, size), color='#5865F2')  # Discord blurple
        draw = ImageDraw.Draw(img)
        
        # Draw a simple music note
        # Note stem
        draw.rectangle([40, 15, 45, 45], fill='white')
        # Note head
        draw.ellipse([35, 40, 50, 55], fill='white')
        
        return img
    
    def _on_show_status(self):
        """Show current playing status in a nice window with album art."""
        import threading
        
        def show_status_window():
            try:
                import tkinter as tk
                from tkinter import ttk
                from PIL import Image, ImageTk
                import requests
                
                # Create window
                window = tk.Tk()
                window.title("NavRPC - Now Playing")
                window.geometry("400x300")
                window.resizable(False, False)
                window.withdraw()

                # Set window icon
                icon_path = self._get_icon_path()
                if icon_path:
                    try:
                        window.iconbitmap(default=icon_path)
                    except Exception:
                        try:
                            icon_img = Image.open(icon_path)
                            window_icon = ImageTk.PhotoImage(icon_img)
                            window.iconphoto(False, window_icon)  # type: ignore[arg-type]
                            window._icon_image = window_icon  # type: ignore[attr-defined]
                        except Exception as e:
                            logger.debug(f"Failed to set window icon: {e}")
                
                # Dark mode colors
                bg_color = "#1e1e1e"
                fg_color = "#ffffff"
                secondary_color = "#808080"
                card_color = "#2d2d2d"
                
                window.configure(bg=bg_color)
                
                # Configure dark mode style
                style = ttk.Style()
                style.theme_use('default')
                
                # Configure styles for dark mode, style="Dark.TFrame"
                style.configure("Dark.TFrame", background=bg_color)
                style.configure("Card.TFrame", background=card_color)
                style.configure("Title.TLabel", 
                              background=bg_color, 
                              foreground=fg_color, 
                              font=("Segoe UI", 12, "bold"))
                style.configure("Info.TLabel", 
                              background=bg_color, 
                              foreground=fg_color, 
                              font=("Segoe UI", 10))
                style.configure("Album.TLabel", 
                              background=bg_color, 
                              foreground=secondary_color, 
                              font=("Segoe UI", 9))
                style.configure("Dark.TButton",
                              background="#3d3d3d",
                              foreground=fg_color,
                              borderwidth=0,
                              focuscolor='none',
                              font=("Segoe UI", 9))
                style.map("Dark.TButton",
                        background=[('active', '#505050'), ('pressed', '#505050')])
                
                # Main frame with padding
                main_frame = ttk.Frame(window, padding="20", style="Dark.TFrame")
                main_frame.pack(fill=tk.BOTH, expand=True)
                
                if self.current_track_info and self.current_track:
                    # Album art section
                    art_frame = ttk.Frame(main_frame)
                    art_frame.pack(pady=(0, 15))
                    
                    logger.debug(f"Album art URL: {self.album_art_url}")
                    
                    # Try to load album art
                    art_label = None
                    
                    # First try cached image data
                    if self.album_art_data:
                        try:
                            logger.info("Using cached album art data")
                            img_data = Image.open(io.BytesIO(self.album_art_data))
                            logger.info(f"Image opened: {img_data.size}, mode: {img_data.mode}")
                            img_data = img_data.resize((150, 150), Image.Resampling.LANCZOS)
                            photo = ImageTk.PhotoImage(img_data)
                            art_label = ttk.Label(art_frame, image=photo)
                            art_label.image = photo  # type: ignore # Keep reference to prevent garbage collection
                            art_label.pack()
                            logger.info("Album art loaded from cache successfully")
                        except Exception as e:
                            logger.error(f"Could not load cached album art: {type(e).__name__}: {e}")
                    
                    # If no cached data, try fetching from URL
                    elif self.album_art_url:
                        try:
                            logger.info(f"Fetching album art from: {self.album_art_url}")
                            response = requests.get(self.album_art_url, timeout=5)
                            logger.info(f"Album art response status: {response.status_code}")
                            
                            if response.status_code == 200:
                                logger.info(f"Received {len(response.content)} bytes of image data")
                                # Cache the image data for future use
                                self.album_art_data = response.content
                                
                                img_data = Image.open(io.BytesIO(response.content))
                                logger.info(f"Image opened: {img_data.size}, mode: {img_data.mode}")
                                img_data = img_data.resize((150, 150), Image.Resampling.LANCZOS)
                                photo = ImageTk.PhotoImage(img_data)
                                art_label = ttk.Label(art_frame, image=photo)
                                art_label.image = photo  # type: ignore # Keep reference to prevent garbage collection
                                art_label.pack()
                                logger.info("Album art loaded and displayed successfully")
                            else:
                                logger.warning(f"Album art request returned status {response.status_code}")
                                if response.status_code == 429:
                                    logger.warning("Imgur rate limit hit - too many requests")
                        except requests.exceptions.RequestException as e:
                            logger.error(f"Network error fetching album art: {e}")
                        except Exception as e:
                            logger.error(f"Could not load album art: {type(e).__name__}: {e}", exc_info=True)
                    
                    # If no album art loaded, show placeholder
                    if art_label is None:
                        logger.info("Showing placeholder album art")
                        placeholder = Image.new('RGB', (150, 150), color='#5865F2')
                        draw = ImageDraw.Draw(placeholder)
                        draw.text((75, 75), "♪", fill='white', anchor='mm', font=None)
                        photo = ImageTk.PhotoImage(placeholder)
                        art_label = ttk.Label(art_frame, image=photo)
                        art_label.image = photo  # type: ignore # Keep reference to prevent garbage collection
                        art_label.pack()
                    
                    # Track info section
                    info_frame = ttk.Frame(main_frame, style="Dark.TFrame")
                    info_frame.pack(fill=tk.BOTH, expand=True)
                    
                    # Title
                    title_label = ttk.Label(info_frame, text=self.current_track_info.get('title', 'Unknown'), 
                                          style="Title.TLabel", wraplength=360)
                    title_label.pack(pady=(0, 5))
                    
                    # Artist
                    artist_label = ttk.Label(info_frame, text=self.current_track_info.get('artist', 'Unknown Artist'), 
                                           style="Info.TLabel", wraplength=360)
                    artist_label.pack(pady=(0, 5))
                    
                    # Album
                    album_label = ttk.Label(info_frame, text=self.current_track_info.get('album', 'Unknown Album'), 
                                          style="Album.TLabel", wraplength=360)
                    album_label.pack(pady=(0, 15))
                else:
                    # No track playing
                    no_track_label = ttk.Label(main_frame, text="No track currently playing", 
                                              style="Info.TLabel")
                    no_track_label.pack(expand=True)
                
                # Close button
                close_btn = ttk.Button(main_frame, text="Close", command=window.destroy, style="Dark.TButton")
                close_btn.pack(pady=(10, 0))
                
                # Center window on main screen
                window.update_idletasks()
                width = window.winfo_width() or window.winfo_reqwidth()
                height = window.winfo_height() or window.winfo_reqheight()
                x = (window.winfo_screenwidth() // 2) - (width // 2)
                y = (window.winfo_screenheight() // 2) - (height // 2)
                window.geometry(f"{width}x{height}+{x}+{y}")
                
                # Make window topmost
                window.attributes('-topmost', True)
                window.focus_force()

                window.deiconify()

                window.mainloop()
                
            except Exception as e:
                logger.error(f"Failed to show status window: {e}")
                # No fallback popup; only log the error
        
        # Run in separate thread to avoid blocking tray event loop
        threading.Thread(target=show_status_window, daemon=True).start()
    
    def _on_show_terminal(self):
        """Open a terminal window showing the log file."""
        try:
            import os
            import subprocess
            
            log_file = "navrpc.log"
            if not os.path.exists(log_file):
                logger.warning("Log file not found")
                return
            
            # Open terminal with log file displayed
            # Use powershell to display the log and keep window open
            cmd = f'powershell -NoExit -Command "Get-Content -Path {log_file} -Wait"'
            subprocess.Popen(cmd, shell=True)
            logger.info("Terminal window opened to show logs")
        except Exception as e:
            logger.error(f"Failed to open terminal: {e}")
    
    def _on_open_config(self):
        """Open the config file in the default editor."""
        try:
            import os
            import subprocess
            config_path = "config.yaml"
            if os.path.exists(config_path):
                # Open with default application
                os.startfile(config_path)
            else:
                logger.warning("Config file not found")
        except Exception as e:
            logger.error(f"Failed to open config: {e}")
    
    def _on_restart(self):
        """Handle restart menu item."""
        logger.info("Restart requested from tray menu")
        if self.on_restart_callback:
            self.on_restart_callback()
    
    def _on_reconnect(self):
        """Handle reconnect menu item."""
        logger.info("Reconnect requested from tray menu")
        if self.on_reconnect_callback:
            self.on_reconnect_callback()
    
    def _on_exit(self):
        """Handle exit menu item."""
        logger.info("Exit requested from tray menu")
        self.stop()
        if self.on_exit_callback:
            self.on_exit_callback()
    
    def _create_menu(self) -> Menu:
        """Create the system tray menu."""
        return Menu(
            MenuItem('Show Status', self._on_show_status, default=True),
            MenuItem('Open Config', self._on_open_config),
            Menu.SEPARATOR,
            MenuItem('Reconnect', self._on_reconnect),
            MenuItem('Restart', self._on_restart),
            Menu.SEPARATOR,
            MenuItem('Exit', self._on_exit)
        )
    
    def update_track(self, track_info: str, title: Optional[str] = None, artist: Optional[str] = None, album: Optional[str] = None, album_art_url: Optional[str] = None, album_art_data: Optional[bytes] = None):
        """
        Update the tooltip with current track information.
        
        Args:
            track_info: String describing the current track (for tooltip)
            title: Track title
            artist: Artist name
            album: Album name
            album_art_url: URL to album art image (for Discord)
            album_art_data: Raw image bytes (for status window)
        """
        self.current_track = track_info
        
        # Update image data if provided
        if album_art_data:
            self.album_art_data = album_art_data
        elif self.album_art_url != album_art_url:
            # URL changed but no data provided - clear cache
            self.album_art_data = None
        
        self.album_art_url = album_art_url
        self.current_track_info = {
            'title': title or 'Unknown',
            'artist': artist or 'Unknown Artist',
            'album': album or 'Unknown Album'
        }
        if self.icon:
            self.icon.title = f"NavRPC - {track_info}"
        
        logger.debug(f"Tray updated - Track: {track_info}, Has image data: {album_art_data is not None}")
    
    def clear_track(self):
        """Clear the current track information."""
        self.current_track = None
        if self.icon:
            self.icon.title = "NavRPC - Idle"
    
    def start(self):
        """Start the system tray icon (runs in current thread)."""
        if self.is_running:
            logger.warning("Tray icon already running")
            return
        
        try:
            self.icon = pystray.Icon(
                "NavRPC",
                icon=self._create_icon_image(),
                title="NavRPC - Starting...",
                menu=self._create_menu()
            )
            self.is_running = True
            logger.info("Starting system tray icon")
            self.icon.run()  # Blocking call
        except Exception as e:
            logger.error(f"Failed to start tray icon: {e}")
            self.is_running = False
    
    def start_in_thread(self):
        """Start the tray icon in a separate thread (non-blocking)."""
        if self.is_running:
            logger.warning("Tray icon already running")
            return
        
        self._tray_thread = threading.Thread(target=self.start, daemon=True)
        self._tray_thread.start()
        logger.info("System tray icon started in background thread")
    
    def stop(self):
        """Stop the system tray icon."""
        if self.icon and self.is_running:
            try:
                self.icon.stop()
                self.is_running = False
                logger.info("System tray icon stopped")
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")

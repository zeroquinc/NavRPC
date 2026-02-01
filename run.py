#!/usr/bin/env python3
"""
Navidrome → Discord Rich Presence with Imgur caching
Entry point for the navrpc package.
"""
import sys
import argparse
import threading
import logging

from navrpc.config import load_config
from navrpc.core import main_loop
from navrpc.validation import validate_configuration
from navrpc.logger import setup_logger, get_logger

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="NavRPC - Navidrome Discord Rich Presence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py              Run NavRPC
  python run.py --debug      Run with debug logging enabled
  python run.py --validate-only  Validate configuration and exit
        """
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--no-log-file',
        action='store_true',
        help='Disable logging to file'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Validate configuration and exit'
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_file = None if args.no_log_file else "navrpc.log"
    setup_logger(level=log_level, log_file=log_file)
    logger = get_logger()
    
    try:
        # Load and validate settings from config.yaml
        logger.info("=" * 60)
        logger.info("NavRPC - Navidrome Discord Rich Presence")
        logger.info("=" * 60)
        
        settings = load_config()
        
        # Validate configuration
        if not validate_configuration(settings):
            logger.error("Configuration validation failed. Please fix errors and try again.")
            sys.exit(1)
        
        # Exit if validation-only mode
        if args.validate_only:
            logger.info("Validation complete. Exiting.")
            sys.exit(0)
        
        # Run with system tray UI
        try:
            from navrpc.tray import TrayIcon
            
            logger.info("Starting NavRPC...")
            logger.info("Right-click the tray icon to access menu options")
            
            # Shared state for restart/reconnect
            restart_event = threading.Event()
            reconnect_event = threading.Event()
            main_thread = None
            
            def restart_app():
                """Restart the entire application."""
                logger.info("Restarting application...")
                import os
                os.execv(sys.executable, [sys.executable] + sys.argv)
            
            def reconnect_discord():
                """Signal to reconnect Discord RPC."""
                logger.info("Reconnecting Discord RPC...")
                reconnect_event.set()
            
            # Create tray icon with callbacks
            tray_icon = TrayIcon(
                on_exit=lambda: sys.exit(0),
                on_restart=restart_app,
                on_reconnect=reconnect_discord
            )
            
            # Start main loop in background thread
            main_thread = threading.Thread(
                target=main_loop, 
                args=(settings, tray_icon),
                daemon=True
            )
            main_thread.start()
            
            # Run tray icon (blocking)
            tray_icon.start()
            
        except ImportError as e:
            logger.error(f"System tray requires pystray: {e}")
            logger.error("Install with: pip install pystray")
            sys.exit(1)
        except Exception as e:
            logger.exception(f"Failed to start: {e}")
            sys.exit(1)
        
    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        logger.error("Please copy 'config.yaml.example' to 'config.yaml' and configure it.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
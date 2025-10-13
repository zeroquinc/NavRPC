#!/usr/bin/env python3
"""
Navidrome → Discord Rich Presence with Imgur caching
Entry point for the navrpc package.
"""
import sys

from navrpc.config import load_config
from navrpc.core import main_loop
from navrpc.client import log

def main():
    try:
        # Load and validate settings from config.yaml
        settings = load_config()
        
        # Start the main polling logic
        main_loop(settings)
        
    except FileNotFoundError as e:
        log(f"Error: {e}")
        log("Please copy 'config.yaml.example' to 'config.yaml' and configure it.")
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
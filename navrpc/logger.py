"""
Enhanced logging module for NavRPC with file and console output support.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

_logger: Optional[logging.Logger] = None

def setup_logger(name: str = "NavRPC", log_file: Optional[str] = "navrpc.log", level: int = logging.INFO) -> logging.Logger:
    """
    Set up the application logger with both file and console handlers.
    
    Args:
        name: Logger name
        log_file: Path to log file. If None, only console logging is enabled
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    _logger = logging.getLogger(name)
    _logger.setLevel(level)
    _logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    _logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)  # File gets all messages
            file_handler.setFormatter(detailed_formatter)
            _logger.addHandler(file_handler)
        except Exception as e:
            _logger.warning(f"Could not set up file logging: {e}")
    
    return _logger

def get_logger() -> logging.Logger:
    """Get the configured logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger

def log(msg: str, level: int = logging.INFO):
    """
    Convenience function for backward compatibility.
    
    Args:
        msg: Message to log
        level: Logging level
    """
    logger = get_logger()
    logger.log(level, msg)

# Convenience functions
def debug(msg: str):
    """Log a debug message."""
    get_logger().debug(msg)

def info(msg: str):
    """Log an info message."""
    get_logger().info(msg)

def warning(msg: str):
    """Log a warning message."""
    get_logger().warning(msg)

def error(msg: str):
    """Log an error message."""
    get_logger().error(msg)

def critical(msg: str):
    """Log a critical message."""
    get_logger().critical(msg)

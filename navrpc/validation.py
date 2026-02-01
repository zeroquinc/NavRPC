"""
Configuration validation and connectivity testing for NavRPC.
"""
from typing import Tuple, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings
from .logger import get_logger

logger = get_logger()

def validate_navidrome_connection(settings: Settings) -> Tuple[bool, Optional[str]]:
    """
    Test connectivity to Navidrome server.
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        session = requests.Session()
        retry_strategy = Retry(total=2, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        params = {
            "u": settings.navidrome.username,
            "p": settings.navidrome.password,
            "v": "1.16.1",
            "c": "nav-rpc",
            "f": "json"
        }
        
        # Test with ping endpoint
        url = f"{settings.navidrome.base_url}/ping"
        response = session.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            logger.info("✓ Navidrome connection successful")
            return True, None
        else:
            error = f"Navidrome returned status {response.status_code}"
            logger.error(f"✗ {error}")
            return False, error
            
    except requests.exceptions.ConnectionError:
        error = "Cannot connect to Navidrome server. Check base_url in config."
        logger.error(f"✗ {error}")
        return False, error
    except requests.exceptions.Timeout:
        error = "Navidrome server connection timed out."
        logger.error(f"✗ {error}")
        return False, error
    except Exception as e:
        error = f"Navidrome validation failed: {e}"
        logger.error(f"✗ {error}")
        return False, error

def validate_discord_client_id(client_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Discord client ID format.
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    if not client_id:
        error = "Discord client ID is empty"
        logger.error(f"✗ {error}")
        return False, error
    
    # Discord IDs should be numeric strings
    if not client_id.isdigit():
        error = f"Discord client ID should be numeric, got: {client_id}"
        logger.error(f"✗ {error}")
        return False, error
    
    # Discord snowflakes are typically 17-20 digits
    if len(client_id) < 17 or len(client_id) > 20:
        error = f"Discord client ID has unusual length: {len(client_id)} digits"
        logger.warning(f"⚠ {error}")
        # Don't fail, just warn
    
    logger.info("✓ Discord client ID format valid")
    return True, None

def validate_imgur_client_id(client_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Imgur client ID format.
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    if not client_id:
        error = "Imgur client ID is empty"
        logger.error(f"✗ {error}")
        return False, error
    
    # Imgur client IDs are typically alphanumeric
    if len(client_id) < 10:
        error = f"Imgur client ID seems too short: {len(client_id)} characters"
        logger.warning(f"⚠ {error}")
    
    logger.info("✓ Imgur client ID format valid")
    return True, None

def validate_configuration(settings: Settings) -> bool:
    """
    Validate all configuration settings and test connections.
    
    Returns:
        True if all validations pass, False otherwise
    """
    logger.info("Validating configuration...")
    
    all_valid = True
    
    # Validate Discord client ID
    discord_valid, discord_error = validate_discord_client_id(
        settings.integration.discord_client_id
    )
    if not discord_valid:
        all_valid = False
    
    # Validate Imgur client ID
    imgur_valid, imgur_error = validate_imgur_client_id(
        settings.integration.imgur_client_id
    )
    if not imgur_valid:
        all_valid = False
    
    # Test Navidrome connection
    nav_valid, nav_error = validate_navidrome_connection(settings)
    if not nav_valid:
        all_valid = False
    
    if all_valid:
        logger.info("✓ All configuration checks passed!")
    else:
        logger.error("✗ Configuration validation failed. Please check your config.yaml")
    
    return all_valid

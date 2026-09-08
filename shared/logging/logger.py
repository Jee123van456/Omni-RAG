import logging
import sys

def setup_logger(name: str = "omnirag") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] - %(message)s'
        )
        
        # Standard output handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger

# Global logger instance
logger = setup_logger()

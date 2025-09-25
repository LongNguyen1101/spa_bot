# logging_config.py
import logging
from rich.logging import RichHandler
from rich.console import Console
from colorama import Fore, Style, init as colorama_init

# Khởi tạo colorama — để Windows cũng hiểu ANSI codes
colorama_init(autoreset=False)

console = Console(force_terminal=True, width=120)

class ColoredLogger:
    """Wrapper class cung cấp các method với màu cố định"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def debug(self, message, color="cyan"):
        self.logger.debug(f"🔍 [{color}]{message}[/{color}]", extra={"markup": True})
    
    def info(self, message, color="bright_magenta"):
        self.logger.info(f"ℹ️  [{color}]{message}[/{color}]", extra={"markup": True})
    
    def warning(self, message, color="orange3"):
        self.logger.warning(f"⚠️  [{color}]{message}[/{color}]", extra={"markup": True})
    
    def error(self, message, color="bright_red"):
        self.logger.error(f"❌ [{color}]{message}[/{color}]", extra={"markup": True})
    
    def critical(self, message, color="bold purple"):
        self.logger.critical(f"🚨 [{color}]{message}[/{color}]", extra={"markup": True})
    
    def success(self, message):
        self.logger.info(f"✅ [bold green]{message}[/bold green]", extra={"markup": True})
    
    def fail(self, message):
        self.logger.error(f"💥 [bold red on yellow]{message}[/bold red on yellow]", extra={"markup": True})
    
    def highlight(self, message):
        self.logger.info(f"⭐ [bold yellow on blue]{message}[/bold yellow on blue]", extra={"markup": True})
    
    def subtle(self, message):
        self.logger.info(f"[dim]{message}[/dim]", extra={"markup": True})

class ANSIColorFormatter(logging.Formatter):
    """
    Formatter để chèn ANSI color escape codes vào message khi ghi file.
    """
    # Màu theo level
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA + Style.BRIGHT,
    }
    
    RESET = Style.RESET_ALL

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.LEVEL_COLORS.get(record.levelno, "")
        return f"{color}{msg}{self.RESET}"

def setup_logging(name: str, log_filename: str = "app.log"):
    # Im lặng các logger “ồn ào”
    for noisy in ['urllib3', 'openai', 'langsmith', 'httpcore', 'httpx']:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    # --- Handler console (Rich) ---
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True
    )
    rich_handler.setLevel(logging.DEBUG)
    # Bạn có thể custom formatter cho console nếu muốn, nhưng RichHandler tự xử tốt.

    # --- Handler file (ghi ANSI màu) ---
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    # Formatter thông thường (thời gian, logger, level, message)
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    ansi_formatter = ANSIColorFormatter(fmt, datefmt=datefmt)
    file_handler.setFormatter(ansi_formatter)

    # Thêm handlers
    logger.addHandler(rich_handler)
    logger.addHandler(file_handler)

    return ColoredLogger(logger)

# Test
if __name__ == "__main__":
    logger = setup_logging("app.test", "test_color.log")
    logger.debug("Debug message - only console & file with color")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.success("Success message")
    logger.critical("Critical message")
    logger.fail("Failed message")
    logger.highlight("Highlighted message")
    logger.subtle("Subtle message")

    print("\n✅ Bạn hãy mở file test_color.log bằng terminal (không phải editor) để xem màu.")

# logging_config.py
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console(force_terminal=True, width=120)

class ColoredLogger:
    """Wrapper class cung cấp các method với màu cố định cho console"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def debug(self, message, color="cyan"):
        self.logger.debug(f"🔍 {message}", extra={"markup": True, "color": color})
    
    def info(self, message, color="bright_magenta"):
        self.logger.info(f"ℹ️  {message}", extra={"markup": True, "color": color})
    
    def warning(self, message, color="orange3"):
        self.logger.warning(f"⚠️  {message}", extra={"markup": True, "color": color})
    
    def error(self, message, color="bright_red"):
        self.logger.error(f"❌ {message}", extra={"markup": True, "color": color})
    
    def critical(self, message, color="bold purple"):
        self.logger.critical(f"🚨 {message}", extra={"markup": True, "color": color})
    
    def success(self, message):
        self.logger.info(f"✅ {message}", extra={"markup": True, "color": "green"})
    
    def fail(self, message):
        self.logger.error(f"💥 {message}", extra={"markup": True, "color": "red"})
    
    def highlight(self, message):
        self.logger.info(f"⭐ {message}", extra={"markup": True, "color": "yellow"})
    
    def subtle(self, message):
        self.logger.info(f"{message}", extra={"markup": True, "color": "dim"})

class PlainFormatter(logging.Formatter):
    """
    Formatter cho file - loại bỏ hoàn toàn markup và ANSI codes
    """
    def format(self, record: logging.LogRecord) -> str:
        # Tạo bản sao record để không ảnh hưởng đến handlers khác
        record_copy = logging.makeLogRecord(record.__dict__)
        
        # Loại bỏ rich markup tags khỏi message
        msg = record_copy.getMessage()
        
        # Loại bỏ [color] tags
        import re
        msg = re.sub(r'\[/?[a-z_\s]+\]', '', msg)
        
        # Gán lại message đã clean
        record_copy.msg = msg
        record_copy.args = ()
        
        return super().format(record_copy)

def setup_logging(name: str, log_filename: str = "app.log"):
    # Im lặng các logger "ồn ào"
    for noisy in ['urllib3', 'openai', 'langsmith', 'httpcore', 'httpx']:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    # --- Handler console (Rich) - CÓ MÀU ---
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True
    )
    rich_handler.setLevel(logging.DEBUG)

    # --- Handler file - KHÔNG MÀU ---
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Formatter plain cho file
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    plain_formatter = PlainFormatter(fmt, datefmt=datefmt)
    file_handler.setFormatter(plain_formatter)

    # Thêm handlers
    logger.addHandler(rich_handler)
    logger.addHandler(file_handler)

    return ColoredLogger(logger)

# Test
if __name__ == "__main__":
    logger = setup_logging("app.test", "test_color.log")
    logger.debug("Debug message - console có màu, file không màu")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.success("Success message")
    logger.critical("Critical message")
    logger.fail("Failed message")
    logger.highlight("Highlighted message")
    logger.subtle("Subtle message")

    print("\n✅ Kiểm tra:")
    print("   - Console: Có màu sắc đẹp")
    print("   - File test_plain.log: Text thuần, không có tag màu")
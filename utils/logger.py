import logging
import os
import glob
import threading
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config.settings import config

class AppLogger:
    """应用日志管理器（线程安全单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return
            self._initialized = True

        self.logger = logging.getLogger('NoteAI')
        self.logger.setLevel(logging.DEBUG)

        self.logger.handlers.clear()
        
        log_dir = Path(config.log_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "noteai.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self._cleanup_old_logs(log_dir)
    
    def _cleanup_old_logs(self, log_dir: Path):
        """清理超过30天的日志文件"""
        try:
            current_time = datetime.now().timestamp()
            for log_file in log_dir.glob("noteai.log*"):
                file_age = current_time - log_file.stat().st_mtime
                if file_age > 30 * 24 * 3600:
                    log_file.unlink()
        except Exception as e:
            self.logger.warning(f"清理旧日志失败: {e}")
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def critical(self, message: str):
        self.logger.critical(message)
    
    def get_logs(self, lines: int = 100) -> list:
        """获取最近的日志"""
        log_file = Path(config.log_path) / "noteai.log"
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            return [f"读取日志失败: {e}"]

# 全局日志实例
logger = AppLogger()

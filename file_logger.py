import time, sys


class FileLogger:
    """
    Simple file logger for MicroPython.
    - Appends lines to a file
    - Adds a timestamp
    - Optional size-based rotation
    """
    def __init__(self, path="log.txt", max_bytes=0, backups=1, flush_each=True):
        """
        path: log file path (e.g. "log.txt" or "/log.txt")
        max_bytes: 0 disables rotation; otherwise rotate when file exceeds this size
        backups: number of rotated backups to keep (log.txt.1, log.txt.2, ...)
        flush_each: flush after each write (safer, slightly slower)
        """
        self.path = path
        self.max_bytes = max_bytes
        self.backups = max(0, int(backups))
        self.flush_each = bool(flush_each)

    def _timestamp(self):
        # If RTC/NTP set, localtime() returns real date/time; otherwise starts at epoch.
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5]
        )

    def _filesize(self):
        try:
            import os
            return os.stat(self.path)[6]
        except OSError:
            return 0

    def _rotate(self):
        if self.max_bytes <= 0 or self.backups <= 0:
            return
        if self._filesize() < self.max_bytes:
            return

        import os

        # Remove oldest
        oldest = "{}.{}".format(self.path, self.backups)
        try:
            os.remove(oldest)
        except OSError:
            pass

        # Shift: .(n-1) -> .n
        for i in range(self.backups - 1, 0, -1):
            src = "{}.{}".format(self.path, i)
            dst = "{}.{}".format(self.path, i + 1)
            try:
                os.rename(src, dst)
            except OSError:
                pass

        # Current -> .1
        try:
            os.rename(self.path, "{}.1".format(self.path))
        except OSError:
            pass

    def log(self, msg, level="INFO", e = None):
        """
        Write one log line.
        msg can be any object; it will be converted to str.
        """
        self._rotate()
        line = "{} [{}] {}\n".format(self._timestamp(), level, msg)

        # Append
        with open(self.path, "a") as f:
            f.write(line)
            if e:
                sys.print_exception(e, f)
            if self.flush_each:
                try:
                    f.flush()
                except AttributeError:
                    pass  # some ports may not expose flush()

    def debug(self, msg): self.log(msg, "DEBUG")
    def info(self, msg):  self.log(msg, "INFO")
    def warn(self, msg):  self.log(msg, "WARN")
    def error(self, msg): self.log(msg, "ERROR")
    def exception(self, msg, e): self.log(msg, "EXCEPTION", e)

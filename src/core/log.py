import logging


class CustomFormatter(logging.Formatter):
    # use ansi escape styles
    # https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797#colors--graphics-mode
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[33m"  # ;21;5
    red = "\x1b[31m"  # ;21
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"  # clears formating
    format_str = "[%(asctime)s] [%(name)s] (%(levelname)s) %(message)s"
    FORMATS = {
        logging.DEBUG: blue + format_str + reset,
        logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record):
        datefmt = "%H:%M:%S"  # "%d.%m.%Y %H:%M:%S"
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt)
        return formatter.format(record)


def set_logging(use_debug):
    """Configure loggers to use a custom formatter for highlighting
    the log level.
    """
    root = logging.getLogger()
    level = logging.DEBUG if use_debug else logging.INFO
    root.setLevel(level)
    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(CustomFormatter())
    root.addHandler(stdout_handler)

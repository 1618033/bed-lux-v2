from file_logger import FileLogger
import logging, gc, micropython, esp32, sys

def show_idf_heap(logger: logging.Logger):
    for i, (total, free, largest, min_free) in enumerate(esp32.idf_heap_info(esp32.HEAP_DATA)):
        logger.debug("HEAP_DATA[%d]: total=%d free=%d largest=%d min_free=%d" % (i, total, free, largest, min_free))

def log_memory_status(logger: logging.Logger, flogger: FileLogger | None=None, simple: bool=True) -> str:
    gc.collect()
    free = gc.mem_free()
    allocated = gc.mem_alloc()
    total = free + allocated

    if not simple:
        logger.debug("------------ Mem ------------------")
        micropython.qstr_info()
        micropython.mem_info()

    text = "Memory: %d/%d bytes free (%d%%)" % (free, total, free * 100 // total)
    logger.debug(text)
    if flogger:
        flogger.debug(text)

    if not simple:
        logger.debug("-----------------------------------")
    
    return text

async def __proto():
    pass

_COROUTINE_TYPE = type(__proto())

def is_coroutine(obj):
    return isinstance(obj, _COROUTINE_TYPE)

def is_awaitable(obj):
    return is_coroutine(obj) or hasattr(obj, "__await__")

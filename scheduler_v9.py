"""V9 scheduler adapter.

Keeps the proven V8 scheduler timing/data-safety flow while routing it through
engine V9 and relabeling diagnostics consistently. Scan cadence remains every
5 minutes; the system-test heartbeat remains every 15 minutes Asia/Bangkok.
"""
import scheduler_v8 as _v8


class _V9LoggerProxy:
    def __init__(self, logger):
        self._logger = logger

    def _msg(self, message):
        return str(message).replace("V8", "V9")

    def warning(self, message, *args, **kwargs):
        return self._logger.warning(self._msg(message), *args, **kwargs)

    def info(self, message, *args, **kwargs):
        return self._logger.info(self._msg(message), *args, **kwargs)

    def error(self, message, *args, **kwargs):
        return self._logger.error(self._msg(message), *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        return self._logger.exception(self._msg(message), *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._logger, name)


_v8.logger = _V9LoggerProxy(_v8.logger)

start = _v8.start
stop = _v8.stop
status = _v8.status
run_scan_cycle = _v8.run_scan_cycle

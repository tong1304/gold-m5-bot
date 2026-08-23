"""V9.2 statistics page adapter."""
import statistics_page_v9 as _v9

_v9._v8.PAGE = _v9._v8.PAGE.replace("Signal Statistics V9", "Signal Statistics V9.2").replace("V9 Pattern / Rejection", "V9.2 Pattern / Rejection").replace("No V9 metadata", "No V9.2 metadata")
register = _v9.register

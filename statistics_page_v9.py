"""V9 statistics page adapter.

Reuses the existing statistics data/API implementation while changing the
presentation labels from V8 to V9. Historical rows keep their stored engine
version, so the page can show mixed legacy history without rewriting data.
"""
import statistics_page_v8 as _v8

# The existing register() closes over PAGE in statistics_page_v8's globals.
# Replace only presentation labels before registering the same routes.
_v8.PAGE = _v8.PAGE.replace("Signal Statistics V8", "Signal Statistics V9").replace("V8 Setup / Rejection", "V9 Pattern / Rejection").replace("No V8 metadata", "No V9 metadata").replace("class=\"v8\"", "class=\"v9\"")

register = _v8.register

"""Structure V8 public entry point.

The implementation is V8-native and no longer depends on engine_v42.
"""
import engine_v8_core
from engine_v8_core import *

base = engine_v8_core
ENGINE_VERSION = engine_v8_core.ENGINE_VERSION
app = engine_v8_core.app

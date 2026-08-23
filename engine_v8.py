"""Structure V8 public entry point.

The implementation is V8-native and no longer depends on engine_v42.
"""
from engine_v8_core import *
import engine_v8_core as base

ENGINE_VERSION = engine_v8_core.ENGINE_VERSION
app = engine_v8_core.app

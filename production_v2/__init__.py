"""Production-v2: isolated nine-engine trading runtime.

The nine brain files are the only cognitive layer.  No sub-engine,
monkey-patch, or import-time brain patch is installed here.
"""

from .pipeline import ProductionPipeline

__all__ = ["ProductionPipeline"]

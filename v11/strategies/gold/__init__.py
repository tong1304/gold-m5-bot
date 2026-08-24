from ..multi_strategy import REGISTRY as _BASE_REGISTRY
from .g3_smc import evaluate as g3_smc_evaluate

# GOLD uses the same independent strategy contract as BTC, but G3 is a
# dedicated SMC Liquidity Sweep + CHoCH + FVG implementation.
REGISTRY = dict(_BASE_REGISTRY)
REGISTRY["LIQUIDITY_SWEEP"] = g3_smc_evaluate

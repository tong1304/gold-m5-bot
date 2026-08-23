from .trend_pullback import evaluate as trend_pullback
from .breakout_retest import evaluate as breakout_retest
from .range_breakout import evaluate as range_breakout
from .momentum import evaluate as momentum
from .volatility_breakout import evaluate as volatility_breakout

REGISTRY={"TREND_PULLBACK":trend_pullback,"BREAKOUT_RETEST":breakout_retest,"RANGE_BREAKOUT":range_breakout,"MOMENTUM":momentum,"VOLATILITY_BREAKOUT":volatility_breakout}

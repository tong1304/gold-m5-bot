from .trend_pullback import evaluate as trend_pullback
from .breakout_retest import evaluate as breakout_retest
from .ema_pullback import evaluate as ema_pullback
from .liquidity_sweep import evaluate as liquidity_sweep
from .sr_reversal import evaluate as sr_reversal
from .volatility_breakout import evaluate as volatility_breakout

REGISTRY={"TREND_PULLBACK":trend_pullback,"BREAKOUT_RETEST":breakout_retest,"EMA_PULLBACK":ema_pullback,"LIQUIDITY_SWEEP":liquidity_sweep,"SR_REVERSAL":sr_reversal,"VOLATILITY_BREAKOUT":volatility_breakout}

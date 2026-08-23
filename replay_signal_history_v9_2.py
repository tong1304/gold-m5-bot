"""V9.2 historical replay adapter.
Reuses the stable V9.1 replay mechanics while replacing its engine with V9.2.
"""
import replay_signal_history_v9_1 as _base
import engine_v9_2 as engine
_base.engine = engine
replay_symbol = _base.replay_symbol
main = _base.main

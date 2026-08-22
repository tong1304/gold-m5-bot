"""Runtime safety overrides loaded automatically by Python before the app.

The live signal engine must never emit a setup below 2:1 risk/reward.
This keeps the minimum independent from older engine defaults.
"""
try:
    import engine_v42 as _base

    _base.MIN_RISK_REWARD = 2.0
    _base.RISK_REWARD = 2.0
except Exception:
    # engine_v42 may not be importable during build-time tooling; the runtime
    # scanner will still apply its own validation once the module is loaded.
    pass

from ...core.subengine import SubEngine as _Base
from .setup_logic import refine_e6


class SubEngine(_Base):
    def __init__(self):
        super().__init__()

    def _analyse(self, data):
        return refine_e6(super()._analyse(data), data, self.sub_engine_id)

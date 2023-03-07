from .fixed import reset as fixed_reset
from .pump import reset as pump_reset


def reset():
    fixed_reset()
    pump_reset()

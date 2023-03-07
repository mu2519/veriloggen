from veriloggen.core.module import Module
from veriloggen.types.pump import c_default, get_pump_mult_packed
from . import stypes


class PumpMult(stypes._BinaryOperator):
    latency = 4

    def __init__(self, a_packed, b_packed, doubled_clock,
                 a_signed: bool = True,
                 b_signed: bool = True,
                 c_width: int | None = None,
                 c_signed: bool | None = None):
        stypes._Operator.__init__(self)

        self.doubled_clock = doubled_clock

        self.a_packed = stypes._to_constant(a_packed)
        self.b_packed = stypes._to_constant(b_packed)
        self.a_packed._add_sink(self)
        self.b_packed._add_sink(self)

        if self.a_packed.get_width() % 2 != 0 or self.b_packed.get_width() % 2 != 0:
            raise ValueError('The width of packed data must be even')
        if self.a_packed.get_signed() or self.b_packed.get_signed():
            raise ValueError('Packed data must be unsigned')

        self.a_width = self.a_packed.get_width() // 2
        self.b_width = self.b_packed.get_width() // 2
        self.a_signed = a_signed
        self.b_signed = b_signed
        c_width, c_signed = c_default(self.a_width, self.b_width, self.a_signed, self.b_signed, c_width, c_signed)
        self.c_width = c_width
        self.c_signed = c_signed

        self.width = self.c_width * 2
        self.signed = False

        self.left = self.a_packed
        self.right = self.b_packed

        self._set_managers()

    def _implement(self, m: Module, seq, svalid=None, senable=None):
        clk1x = m._clock
        clk2x = self.doubled_clock
        rst = m._reset

        c_packed = m.Wire(self.name('c_packed'), self.get_width(), signed=self.get_signed())
        self.sig_data = c_packed

        pump_mult_packed = get_pump_mult_packed(self.a_width, self.b_width, self.a_signed, self.b_signed, self.c_width, self.c_signed)

        ports = [
            ('clk1x', clk1x), ('clk2x', clk2x), ('rst', rst),
            ('a_packed', self.a_packed.sig_data),
            ('b_packed', self.b_packed.sig_data),
            ('c_packed', c_packed),
        ]

        m.Instance(pump_mult_packed, self.name('pump_mult_packed'), ports=ports)

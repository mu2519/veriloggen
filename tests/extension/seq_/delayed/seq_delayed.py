from __future__ import absolute_import
from __future__ import print_function
import sys
import os
import math

# the next line can be removed after installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from veriloggen import *


def mkLed(numports=8, delay_amount=2):
    m = Module('blinkled')
    clk = m.Input('CLK')
    rst = m.Input('RST')
    led = [m.OutputReg('led' + str(i), initval=0) for i in range(numports)]

    seq = Seq(m, 'seq', clk, rst)

    count = m.Reg('count', (numports - 1).bit_length(), initval=0)
    seq(
        count.inc()
    )

    for i in range(numports):
        seq.If(count == i)(
            led[i](1)
        )
        seq.If(count == i).Delay(delay_amount)(
            led[i](0)
        )

    seq.make_always()

    return m


def mkTest():
    m = Module('test')

    # target instance
    led = mkLed()

    # copy paras and ports
    params = m.copy_params(led)
    ports = m.copy_sim_ports(led)

    clk = ports['CLK']
    rst = ports['RST']

    uut = m.Instance(led, 'uut',
                     params=m.connect_params(led),
                     ports=m.connect_ports(led))

    # vcd_name = os.path.splitext(os.path.basename(__file__))[0] + '.vcd'
    # simulation.setup_waveform(m, uut, dumpfile=vcd_name)
    simulation.setup_clock(m, clk, hperiod=5)
    init = simulation.setup_reset(m, rst, period=100)

    nclk = simulation.next_clock

    init.add(
        Delay(1000),
        Systask('finish'),
    )

    return m


if __name__ == '__main__':
    test = mkTest()
    verilog = test.to_verilog('tmp.v')
    print(verilog)

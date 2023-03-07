from __future__ import annotations

from veriloggen.core.module import Module
from veriloggen.core.vtypes import Cat, Cond, If, Posedge


def c_default(
    a_width: int,
    b_width: int,
    a_signed: bool,
    b_signed: bool,
    c_width: int | None,
    c_signed: bool | None,
) -> tuple[int, bool]:
    if c_width is None:
        c_width = a_width + b_width
    if c_signed is None:
        c_signed = a_signed or b_signed
    return c_width, c_signed


# based on https://docs.xilinx.com/r/en-US/ug901-vivado-synthesis/Unsigned-16x24-Bit-Multiplier-Coding-Example-Verilog
def make_mult(
    index: int,
    a_width: int,
    b_width: int,
    a_signed: bool = True,
    b_signed: bool = True,
    c_width: int | None = None,
    c_signed: bool | None = None,
    operand_pipeline_depth: int = 1,
    result_pipeline_depth: int = 3,
) -> Module:
    c_width, c_signed = c_default(
        a_width, b_width, a_signed, b_signed, c_width, c_signed)

    m = Module(f'mult_{index}')

    clk = m.Input('clk')
    a = m.Input('a', a_width)
    b = m.Input('b', b_width)
    c = m.Output('c', c_width)

    a_reg_list = [m.Reg(f'a_reg_{i}', a_width, signed=a_signed)
                  for i in range(operand_pipeline_depth)]
    b_reg_list = [m.Reg(f'b_reg_{i}', b_width, signed=b_signed)
                  for i in range(operand_pipeline_depth)]
    c_reg_list = [m.Reg(f'c_reg_{i}', c_width, signed=c_signed)
                  for i in range(result_pipeline_depth)]

    m.Always(Posedge(clk))(
        a_reg_list[0](a),
        *[a_reg_list[i + 1](a_reg_list[i])
          for i in range(operand_pipeline_depth - 1)],
        b_reg_list[0](b),
        *[b_reg_list[i + 1](b_reg_list[i])
          for i in range(operand_pipeline_depth - 1)],
        c_reg_list[0](a_reg_list[-1] * b_reg_list[-1]),
        *[c_reg_list[i + 1](c_reg_list[i])
          for i in range(result_pipeline_depth - 1)],
    )

    m.Assign(c(c_reg_list[-1]))

    return m


# based on https://docs.xilinx.com/v/u/en-US/xapp706
def make_pump_mult(
    index: int,
    a_width: int,
    b_width: int,
    a_signed: bool = True,
    b_signed: bool = True,
    c_width: int | None = None,
    c_signed: bool | None = None,
) -> Module:
    c_width, c_signed = c_default(
        a_width, b_width, a_signed, b_signed, c_width, c_signed)

    m = Module(f'pump_mult_{index}')

    clk1x = m.Input('clk1x')
    clk2x = m.Input('clk2x')
    rst = m.Input('rst')

    a0 = m.Input('a0', a_width, signed=a_signed)
    a1 = m.Input('a1', a_width, signed=a_signed)
    b0 = m.Input('b0', b_width, signed=b_signed)
    b1 = m.Input('b1', b_width, signed=b_signed)
    a0_reg = m.Reg('a0_reg', a_width, signed=a_signed)
    a1_reg = m.Reg('a1_reg', a_width, signed=a_signed)
    b0_reg = m.Reg('b0_reg', b_width, signed=b_signed)
    b1_reg = m.Reg('b1_reg', b_width, signed=b_signed)
    m.Always(Posedge(clk1x))(
        a0_reg(a0),
        a1_reg(a1),
        b0_reg(b0),
        b1_reg(b1),
    )

    follow_clk1x = m.Reg('follow_clk1x')
    toggle = m.Reg('toggle')
    toggle_1 = m.Reg('toggle_1')
    m.Always(Posedge(clk1x))(
        If(rst)(
            toggle(0)
        ).Else(
            toggle(~toggle)
        )
    )
    m.Always(Posedge(clk2x))(
        toggle_1(toggle)
    )
    m.Always(Posedge(clk2x))(
        follow_clk1x(~(toggle ^ toggle_1))
    )

    mux_sel = m.Reg('mux_sel')
    m.Always(Posedge(clk2x))(
        mux_sel(follow_clk1x)
    )

    a = m.Wire('a', a_width, signed=a_signed)
    b = m.Wire('b', b_width, signed=b_signed)
    m.Assign(a(Cond(mux_sel, a1_reg, a0_reg)))
    m.Assign(b(Cond(mux_sel, b1_reg, b0_reg)))

    c = m.Wire('c', c_width, signed=c_signed)
    mult = make_mult(
        index, a_width, b_width, a_signed, b_signed, c_width, c_signed,
        operand_pipeline_depth=2, result_pipeline_depth=2)
    ports = [('clk', clk2x), ('a', a), ('b', b), ('c', c)]
    m.Instance(mult, 'mult', ports=ports)

    c0 = m.Output('c0', c_width, signed=c_signed)
    c1 = m.Output('c1', c_width, signed=c_signed)
    c0_reg = m.Reg('c0_reg', c_width, signed=c_signed)
    c1_reg = m.Reg('c1_reg', c_width, signed=c_signed)
    c_delay_reg = m.Reg('c_delay_reg', c_width, signed=c_signed)
    m.Always(Posedge(clk2x))(
        c_delay_reg(c)
    )
    m.Always(Posedge(clk1x))(
        c0_reg(c_delay_reg),
        c1_reg(c),
    )
    m.Assign(c0(c0_reg))
    m.Assign(c1(c1_reg))

    return m


def make_pump_mult_packed(
    index: int,
    a_width: int,
    b_width: int,
    a_signed: bool = True,
    b_signed: bool = True,
    c_width: int | None = None,
    c_signed: bool | None = None,
) -> Module:
    c_width, c_signed = c_default(
        a_width, b_width, a_signed, b_signed, c_width, c_signed)

    m = Module(f'pump_mult_packed_{index}')

    clk1x = m.Input('clk1x')
    clk2x = m.Input('clk2x')
    rst = m.Input('rst')
    a_packed = m.Input('a_packed', a_width * 2, signed=False)
    b_packed = m.Input('b_packed', b_width * 2, signed=False)
    c_packed = m.Output('c_packed', c_width * 2, signed=False)

    a0 = m.Wire('a0', a_width, signed=a_signed)
    a1 = m.Wire('a1', a_width, signed=a_signed)
    b0 = m.Wire('b0', b_width, signed=b_signed)
    b1 = m.Wire('b1', b_width, signed=b_signed)
    c0 = m.Wire('c0', c_width, signed=c_signed)
    c1 = m.Wire('c1', c_width, signed=c_signed)

    Cat(a1, a0).assign(a_packed)
    Cat(b1, b0).assign(b_packed)
    c_packed.assign(Cat(c1, c0))

    pump_mult = make_pump_mult(
        index, a_width, b_width, a_signed, b_signed, c_width, c_signed)
    ports = [
        ('clk1x', clk1x), ('clk2x', clk2x), ('rst', rst),
        ('a0', a0), ('a1', a1), ('b0', b0), ('b1', b1), ('c0', c0), ('c1', c1),
    ]
    m.Instance(pump_mult, 'pump_mult', ports=ports)

    return m


index_count = 0


def reset():
    global index_count
    index_count = 0


def get_pump_mult(
    a_width: int,
    b_width: int,
    a_signed: bool = True,
    b_signed: bool = True,
    c_width: int | None = None,
    c_signed: bool | None = None,
) -> Module:
    global index_count
    pump_mult = make_pump_mult(
        index_count, a_width, b_width, a_signed, b_signed, c_width, c_signed)
    index_count += 1
    return pump_mult


def get_pump_mult_packed(
    a_width: int,
    b_width: int,
    a_signed: bool = True,
    b_signed: bool = True,
    c_width: int | None = None,
    c_signed: bool | None = None,
) -> Module:
    global index_count
    pump_mult_packed = make_pump_mult_packed(
        index_count, a_width, b_width, a_signed, b_signed, c_width, c_signed)
    index_count += 1
    return pump_mult_packed

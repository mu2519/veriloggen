import random

import numpy as np

from veriloggen import *
import veriloggen.thread as vthread
from veriloggen.types import axi
from veriloggen.types.ipxact import to_ipxact


in_log_word = 1
in_datawidth = (1 << in_log_word) * 8

out_log_word = 2
out_datawidth = (1 << out_log_word) * 8

# the capacity of memory (in bytes)
memory_capacity = 2**20

axi_max_datawidth = 128
axi_addrwidth = 32

axilite_datawidth = 32
axilite_addrwidth = 32
axireg_length = 9

simulation_period = 10000000

rand_range = (-16, 16)

size_0 = 32
size_1 = 32
size_2 = 32

a_offset = 0 * 256 * 1024
b_offset = 1 * 256 * 1024
c_offset = 2 * 256 * 1024
c_ref_offset = 3 * 256 * 1024

log_parallelism = 3
parallelism = 1 << log_parallelism
packed_datawidth = in_datawidth * parallelism
axi_wide_width = min(packed_datawidth, axi_max_datawidth)

log_blocksize_0 = 2
log_blocksize_1 = 4
log_blocksize_2 = 2
blocksize_0 = 1 << log_blocksize_0
blocksize_1 = 1 << log_blocksize_1
blocksize_2 = 1 << log_blocksize_2


def mkdut():
    m = Module('gemm_blocked_ram')
    clk = m.Input('CLK')
    rst = m.Input('RST')

    counter = m.Reg('counter', 64, initval=0)
    seq = Seq(m, 'seq', clk, rst)
    seq(
        counter.inc()
    )

    ram_a = vthread.RAM(m, 'ram_a', clk, rst, packed_datawidth, log_blocksize_1 - log_parallelism)
    ram_b = vthread.RAM(m, 'ram_b', clk, rst, packed_datawidth, log_blocksize_1 + log_blocksize_2 - log_parallelism)
    ram_c = vthread.RAM(m, 'ram_c', clk, rst, out_datawidth, log_blocksize_0 + log_blocksize_2)

    strm = vthread.Stream(m, 'mac', clk, rst)
    size = strm.parameter('size', 32)
    initval = strm.parameter('initval', out_datawidth)
    a_packed = strm.source('a', packed_datawidth)
    b_packed = strm.source('b', packed_datawidth)
    a_list = strm.Split(a_packed, in_datawidth)
    b_list = strm.Split(b_packed, in_datawidth)
    prod_list = [a * b for a, b in zip(a_list, b_list)]
    sum = strm.AddTree(*prod_list)
    c, c_valid = strm.ReduceAddValid(sum, size, initval=initval)
    strm.sink(c, 'c', c_valid, 'c_valid')

    axi_narrow = vthread.AXIM(m, 'axi_narrow', clk, rst, datawidth=out_datawidth, addrwidth=axi_addrwidth)
    axi_wide = vthread.AXIM(m, 'axi_wide', clk, rst, datawidth=axi_wide_width, addrwidth=axi_addrwidth)

    saxi = vthread.AXISLiteRegister(m, 'saxi', clk, rst,
                                    datawidth=axilite_datawidth,
                                    addrwidth=axilite_addrwidth,
                                    length=axireg_length)

    def main():
        while True:
            saxi.wait_flag(0, 1)
            saxi.write(1, 1)  # set busy

            start: 64 = counter

            size_0 = saxi.read(3)
            size_1 = saxi.read(4)
            size_2 = saxi.read(5)
            a_offset = saxi.read(6)
            b_offset = saxi.read(7)
            c_offset = saxi.read(8)

            comp(size_0, size_1, size_2, a_offset, b_offset, c_offset)

            stop: 64 = counter

            time = stop - start
            saxi.write(2, time)

            saxi.write(1, 0)  # unset busy

    def comp(size_0, size_1, size_2, a_offset, b_offset, c_offset):
        for i in range(0, size_0, blocksize_0):
            for j in range(0, size_2, blocksize_2):
                for k in range(0, size_1, blocksize_1):
                    b_addr: 'multicycle' = ((j*size_1 + k) << in_log_word) + b_offset
                    for b_idx in range(0, blocksize_1 * blocksize_2 // parallelism, blocksize_1 // parallelism):
                        axi_wide.dma_read(ram_b, b_idx, b_addr, blocksize_1 // parallelism)
                        b_addr += size_1 << in_log_word

                    a_addr: 'multicycle' = ((i*size_1 + k) << in_log_word) + a_offset
                    for ii in range(0, blocksize_0 * blocksize_2, blocksize_2):
                        axi_wide.dma_read(ram_a, 0, a_addr, blocksize_1 // parallelism)

                        for jj in range(blocksize_2):
                            if k == 0:
                                initval = 0
                            else:
                                initval = ram_c.read(ii + jj)
                            strm.set_parameter('size', blocksize_1 // parallelism)
                            strm.set_parameter('initval', initval)
                            strm.set_source('a', ram_a, 0, blocksize_1 // parallelism)
                            strm.set_source('b', ram_b, jj << (log_blocksize_1 - log_parallelism), blocksize_1 // parallelism)
                            strm.set_sink('c', ram_c, ii + jj, 1)
                            strm.run()
                            strm.join()

                        a_addr += size_1 << in_log_word

                c_addr: 'multicycle' = ((i*size_2 + j) << out_log_word) + c_offset
                for c_idx in range(0, blocksize_0 * blocksize_2, blocksize_2):
                    axi_narrow.dma_write(ram_c, c_idx, c_addr, blocksize_2)
                    c_addr += size_2 << out_log_word

    thd = vthread.Thread(m, 'thd', clk, rst, main)
    thd.start()

    return m


def mktb():
    random.seed(0, 2)

    a = np.zeros((size_0, size_1), dtype=np.int64)  # A is row major
    b = np.zeros((size_2, size_1), dtype=np.int64)  # B is column major
    for i in range(size_0):
        for j in range(size_1):
            a[i, j] = random.randint(*rand_range)
    for i in range(size_1):
        for j in range(size_2):
            b[j, i] = random.randint(*rand_range)
    c_ref = a @ b.T  # C is row major
    assert c_ref.shape == (size_0, size_2)
    assert c_ref.dtype == np.int64

    in_mem_img = np.zeros(memory_capacity, dtype=np.int64)
    axi.set_memory(in_mem_img, a, in_datawidth, in_datawidth, a_offset)
    axi.set_memory(in_mem_img, b, in_datawidth, in_datawidth, b_offset)
    out_mem_img = np.zeros(memory_capacity, dtype=np.int64)
    axi.set_memory(out_mem_img, c_ref, out_datawidth, out_datawidth, c_ref_offset)

    dut = mkdut()

    m = Module('tb')
    params = m.copy_params(dut)
    ports = m.copy_sim_ports(dut)
    clk = ports['CLK']
    rst = ports['RST']

    in_memory = axi.AxiMemoryModel(m, 'in_memory', clk, rst, datawidth=axi_wide_width, addrwidth=axi_addrwidth, mem_datawidth=in_datawidth, mem_addrwidth=0, memimg=in_mem_img, memimg_name='in_mem_img', memimg_datawidth=in_datawidth)
    out_memory = axi.AxiMemoryModel(m, 'out_memory', clk, rst, datawidth=out_datawidth, addrwidth=axi_addrwidth, mem_datawidth=out_datawidth, mem_addrwidth=0, memimg=out_mem_img, memimg_name='out_mem_img', memimg_datawidth=out_datawidth)
    in_memory.connect(ports, 'axi_wide')
    out_memory.connect(ports, 'axi_narrow')

    _saxi = vthread.AXIMLite(m, '_saxi', clk, rst,
                             datawidth=axilite_datawidth,
                             addrwidth=axilite_addrwidth, noio=True)
    _saxi.connect(ports, 'saxi')

    axilite_wordsize = axilite_datawidth // 8

    def ctrl():
        for i in range(100):
            pass

        _saxi.write(axilite_wordsize * 3, size_0)
        _saxi.write(axilite_wordsize * 4, size_1)
        _saxi.write(axilite_wordsize * 5, size_2)
        _saxi.write(axilite_wordsize * 6, a_offset)
        _saxi.write(axilite_wordsize * 7, b_offset)
        _saxi.write(axilite_wordsize * 8, c_offset)

        # set start
        _saxi.write(axilite_wordsize * 0, 1)

        # wait not busy
        while True:
            busy = _saxi.read(axilite_wordsize * 1)
            if not busy:
                break

        time = _saxi.read(axilite_wordsize * 2)

        flag = True
        for i in range(size_0):
            for j in range(size_2):
                x = out_memory.read(c_offset + (size_2*i + j)*(out_datawidth//8))
                y = out_memory.read(c_ref_offset + (size_2*i + j)*(out_datawidth//8))
                if x != y:
                    flag = False

        if flag:
            print('AC')
        else:
            print('WA')

        print('exec time:', time)

        vthread.finish()

    thd = vthread.Thread(m, 'thd', clk, rst, ctrl)
    thd.start()

    m.Instance(dut, 'dut',
               params=m.connect_params(dut),
               ports=m.connect_ports(dut))

    simulation.setup_clock(m, clk, hperiod=10)
    init = simulation.setup_reset(m, rst, m.make_reset(), period=100)
    init.add(
        Delay(simulation_period),
        Systask('finish')
    )

    return m


def run():
    tb = mktb()
    sim = simulation.Simulator(tb, sim='iverilog')
    rslt = sim.run()
    print(rslt)


def syn():
    m = mkdut()
    to_ipxact(m, clk_ports=[('CLK', ('RST',))], rst_ports=[('RST', 'ACTIVE_HIGH')])


if __name__ == '__main__':
    run()
    syn()

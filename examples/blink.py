from collections import namedtuple
from amaranth import *
from amaranth.build import Resource, Pins
from amaranth.cli import main
from amaranth.sim import *
from amaranth_boards.icestick import ICEStickPlatform
import warnings

import sys
# works if run from repo root
sys.path.append(".")
# works if run from examples dir
sys.path.append("..")
from pulser import PulseStep, PLL, Trigger


class Top(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.enable = Signal()

    def elaborate(self, platform):
        m = Module()

        # You apparently really needs the dir='-' thing
        clk_pin = platform.request(platform.default_clk, dir='-')

        freq_out = 204
        pll = PLL(12, freq_out)

        led = platform.request('led', 0)

        platform.add_resources([
            Resource("pin0", 0, Pins("1", dir="i", conn=("pmod", 0))),
            Resource("pin1", 0, Pins("2", dir="o", conn=("pmod", 0))),
        ])
        con0 = platform.request("pin0", 0)
        con1 = platform.request("pin1", 0)

        # Define the rest of them to force them off
        led1 = platform.request('led', 1)
        led2 = platform.request('led', 2)
        led3 = platform.request('led', 3)
        off = Const(0)

        # Override default sync domain
        m.domains += pll.domain

        tstep = 1 / (freq_out * 1e6)

        def t2c(t):
            return int(t/tstep)

        # Example pulse train
        p1 = PulseStep(1)
        p2 = PulseStep(204 * 1000000)  # HI
        p3 = PulseStep(204 * 1000000)
        p4 = PulseStep(204 * 1000000)  # HI
        p5 = PulseStep(204 * 1000000)
        p6 = PulseStep(204 * 1000000)  # HI

        # Trigger to start pulse train
        t = Trigger(6 * 204 * 1000000)

        m.submodules += [
            pll,
            t,
            p1,
            p2,
            p3,
            p4,
            p5,
            p6,
        ]

        m.d.comb += [
            pll.clk_pin.eq(clk_pin),
            t.trig_in.eq(C(1)),
            p1.input.eq(self.start),
            p1.prev.eq(t.trigger),
            p1.en.eq(t.trigger),
            p2.input.eq(p1.output),
            p2.prev.eq(p1.next),
            p2.en.eq(t.trigger),
            p3.input.eq(p2.output),
            p3.prev.eq(p2.next),
            p3.en.eq(t.trigger),
            p4.input.eq(p3.output),
            p4.prev.eq(p3.next),
            p4.en.eq(t.trigger),
            p5.input.eq(p4.output),
            p5.prev.eq(p4.next),
            p5.en.eq(t.trigger),
            p6.input.eq(p5.output),
            p6.prev.eq(p5.next),
            p6.en.eq(t.trigger),
            con1.eq(p6.output),

            led.eq(p6.output),
            led1.eq(off),
            led2.eq(off),
            led3.eq(off),
        ]

        return m


if __name__ == '__main__':
    platform = ICEStickPlatform()
    platform.build(Top(), do_program=True)

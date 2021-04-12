from collections import namedtuple
from nmigen import *
from nmigen.cli import main
from nmigen.sim import *
from nmigen_boards.icestick import ICEStickPlatform
import warnings

import sys
sys.path.append(".")
from lib.pulsestep import PulseStep
from lib.pll import PLL
from lib.trigger import Trigger


class Top(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.enable = Signal()

    def elaborate(self, platform):
        m = Module()

        # You apparently really needs the dir='-' thing
        clk_pin = platform.request(platform.default_clk, dir='-')
        pll = PLL(12, 204)

        led = platform.request('led', 0)

        # Define the rest of them to force them off
        led1 = platform.request('led', 1)
        led2 = platform.request('led', 2)
        led3 = platform.request('led', 3)
        off = Const(0)

        # Override default sync domain
        m.domains += pll.domain

        # Example pulse train
        p1 = PulseStep(1)
        p2 = PulseStep(204_000_000)  # HI
        p3 = PulseStep(204_000_000)
        p4 = PulseStep(204_000_000)  # HI

        # Trigger to start pulse train
        t = Trigger(1, 2_000_000_000)

        m.submodules += [
            pll,
            t,
            p1,
            p2,
            p3,
            p4,
        ]

        m.d.comb += [
            pll.clk_pin.eq(clk_pin),
            t.trig_in.eq(1),
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
            led.eq(p4.output),

            led1.eq(off),
            led2.eq(off),
            led3.eq(off),
        ]

        return m


if __name__ == '__main__':
    platform = ICEStickPlatform()
    platform.build(Top(), do_program=False)

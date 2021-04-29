from collections import namedtuple
from nmigen import *
from nmigen.build import Resource, Pins
from nmigen_boards.icestick import ICEStickPlatform
import getopt
import sys

from .lib.pulsestep import PulseStep
from .lib.pll import PLL
from .lib.trigger import Trigger


def usage():
    print("pulser [ -f freq | -p period] [-nu] t1 t2 ...")
    print("")
    print("OPTIONS:")
    print("  -f  Clock frequency in MHz (16 - 275) [default: 60]")
    print("  -h  Print this text")
    print("  -n  Args interpreted as ns, not cycles")
    print("  -p  Clock period in ns (~ 3.6 - 62.5)")
    print("  -u  Upload to the FPGA [default: false]")
    print("  -v  Version")
    print("")
    print("For -p and -n, beware integer division")
    print("")
    print("ARGUMENTS:")
    print("  t1 t2 ...")
    print("  Time in cycles (or ns if -n) before toggling output pin")
    print("  Output starts low, t1 is the delay after trigger (min 1)")
    print("  Number of args must be even")


def version():
    print("pulser 1.0")
    print("License: 0BSD")
    print("Bob Peterson <bob@rwp.is>")


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        optlist, args = getopt.getopt(args, "f:hnp:uv")
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)
    freq = 60
    fdef = False
    nsunit = False
    upload = False
    for o, a in optlist:
        if o == '-v':
            version()
            sys.exit()
        elif o == '-h':
            usage()
            sys.exit()
        elif o == '-n':
            nsunit = True
        elif o == '-u':
            upload = True
        elif o == '-f':
            if fdef:
                print("Specify only -f or -p")
                sys.exit(2)
            else:
                fdef = True
                freq = int(a)
        elif o == '-p':
            if fdef:
                print("Specify only -f or -p")
                sys.exit(2)
            else:
                fdef = True
                freq = 1.0 / int(a)
        else:
            print("unhandled option")
            sys.exit(2)

    if (len(args) % 2 == 1) or (len(args) < 2):
        print("number of args must be even and greater than 2")
        sys.exit(3)
    times = []
    for arg in args:
        if nsunit:
            # Number of clock periods this time takes
            times.append(int(arg / freq))
        else:
            # Number of clock periods directly
            times.append(int(arg))


    class Pulser(Elaboratable):
        def __init__(self):
            self.start = Signal()
            self.enable = Signal()

        def elaborate(self, platform):
            m = Module()

            # You apparently really needs the dir='-' thing
            clk_pin = platform.request(platform.default_clk, dir='-')

            freq_out = freq
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

            # Assemble the pulse sequence
            p = []
            for time in times:
                p.append(PulseStep(time))

            # Trigger to start pulse train
            t = Trigger(sum(times))

            m.submodules += [
                pll,
                t,
            ]
            for ps in p:
                m.submodules += ps

            m.d.comb += [
                pll.clk_pin.eq(clk_pin),
                t.trig_in.eq(con0),
                p[0].input.eq(self.start),
                p[0].prev.eq(t.trigger),
                p[0].en.eq(t.trigger),
                # fill in 1 to -2 below...
                p[-1].input.eq(p[-2].output),
                p[-1].prev.eq(p[-2].next),
                p[-1].en.eq(t.trigger),
                con1.eq(p[-1].output),

                led.eq(off),
                led1.eq(off),
                led2.eq(off),
                led3.eq(off),
            ]

            for i in range(1, len(p) - 1):
                m.d.comb += [
                    p[i].input.eq(p[i - 1].output),
                    p[i].prev.eq(p[i - 1].next),
                    p[i].en.eq(t.trigger),
                ]

            return m

    platform = ICEStickPlatform()
    platform.build(Pulser(), do_program=upload)

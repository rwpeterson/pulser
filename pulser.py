from collections import namedtuple
from nmigen import *
from nmigen.cli import main
from nmigen.sim import *
from nmigen_boards.icebreaker import ICEBreakerPlatform
import warnings


class PulseStep(Elaboratable):
    """Chainable pulse step primitive.

    Parameters
    ----------
    duration : int
        Duration of pulse step

    Attributes
    ----------
    trigger: in
        Input trigger
    input: in
        Input state
    output: out
        Output state, follows input before trigger, but is then negated
    done: out
        End status chainable to next input trigger

    Chaining
    --------
    ```
           +--------------------+     +--------------------+
    i  --> | input->[~]->output | --> | input->[~]->output | --> pulse_out
           |         ^          |     |         ^          |
           |  dur_0  |          |     |  dur_1  |          |
    1  --> | !{ctr}->?--> done  | --> | !{ctr}->?--> done  | --> _
           +--------------------+     +--------------------+
    ```
    Starting from an initial state i, the state of pulse_out is toggled every
    dur_j cycles by subsequent chained PulseStep instances. The (j+1)st
    instance is started via the jth instance setting done to high when ctr = -1
    """

    def __init__(self, duration):
        self.duration = duration
        self.en = Signal()
        self.input = Signal()
        self.output = Signal()
        self.done = Signal()

        self.ports = [
            self.en,
            self.input,
            self.output,
            self.done,
        ]

    def elaborate(self, platform):
        # It seems cheap on FPGAs to only check one bit of a number instead of
        # some arbitrary value, so loops often count down and terminate at -1,
        # where you can just monitor the MSB of a signed signal.

        # We can use a range() to set the signal's shape automatically
        ctr = Signal(range(-1, self.duration - 1), reset=(self.duration - 2))

        m = Module()

        # Enabled
        with m.If(self.en):
            # Finished counting
            with m.If(ctr[-1]):
                # Toggle output and set done
                with m.If(~(self.done)):
                    m.d.comb += [
                        # Indicate done
                        self.done.eq(1),
                    ]
                # Always invert (final state)
                m.d.comb += [
                    # Invert input
                    self.output.eq(~self.input),
                ]
            # Still counting
            with m.Else():
                m.d.sync += [
                    # Decrement counter
                    ctr.eq(ctr - 1),
                ]
                m.d.comb += [
                    # Keep buffering input
                    self.output.eq(self.input)
                ]
        # Disabled
        with m.Else():
            # Buffer input
            m.d.comb += [
                self.output.eq(self.input),
            ]

        return m


class PLL(Elaboratable):
    """Set the PLL to produce a higher-frequency clock.

    Currently, there is not a way to [express PLL primitives][i] directly in
    nMigen. We use Instance to instantiate a Verilog module directly--in this
    case the one produced by `icepll`.

    For reference, see the [Instance source][n], example implementations
    ([1][e1] and [2][e2]), and a [blog post] on adapting them to the ICEStick.

    [i]: https://github.com/nmigen/nmigen/issues/425
    [n]: https://github.com/nmigen/nmigen/blob/master/nmigen/hdl/ir.py
    [e1]: https://github.com/tpwrules/tasha_and_friends/blob/eventuator/tasha/gateware/icebreaker/pll.py
    [e2]: https://github.com/kbob/nmigen-examples/blob/master/nmigen_lib/pll.py
    [b]: http://41j.com/blog/2020/01/nmigen-pll-ice40hx8k-hx1k/
    """

    def __init__(self, freq_in, freq_out, domain_name="sync"):
        self.freq_in = freq_in
        self.freq_out = freq_out
        self.coeff = self._calc_freq_coefficients()
        
        self.clk_pin = Signal()

        self.domain_name = domain_name
        self.domain = ClockDomain(domain_name)

        self.ports = [
            self.clk_pin,
            self.domain.clk,
            self.domain.rst,
        ]

    def _calc_freq_coefficients(self):
        # cribbed from Icestorm's icepll.
        f_in, f_req = self.freq_in, self.freq_out
        assert 10 <= f_in <= 13
        assert 16 <= f_req <= 275
        coefficients = namedtuple('coefficients', 'divr divf divq')
        divf_range = 128        # see comments in icepll.cc
        best_fout = float('inf')
        for divr in range(16):
            pfd = f_in / (divr + 1)
            if 10 <= pfd <= 133:
                for divf in range(divf_range):
                    vco = pfd * (divf + 1)
                    if 533 <= vco <= 1066:
                        for divq in range(1, 7):
                            fout = vco * 2**-divq
                            if abs(fout - f_req) < abs(best_fout - f_req):
                                best_fout = fout
                                best = coefficients(divr, divf, divq)
        if best_fout != f_req:
            warnings.warn(
                f'PLL: requested {f_req} MHz, got {best_fout} MHz)',
                stacklevel=3)
        return best

    def elaborate(self, platform):
        pll_lock = Signal()
        pll = Instance(
            "SB_PLL40_CORE",
            p_FEEDBACK_PATH='SIMPLE',
            p_DIVR=self.coeff.divr,
            p_DIVF=self.coeff.divf,
            p_DIVQ=self.coeff.divq,
            p_FILTER_RANGE=0b001,

            i_REFERENCECLK=self.clk_pin,
            i_RESETB=Const(1),
            i_BYPASS=Const(0),

            # CORE, not GLOBAL?
            o_PLLOUTCORE=ClockSignal(self.domain_name),
            o_LOCK=pll_lock
            )

        rs = ResetSynchronizer(~(self.pll_lock), domain=self.domain_name)

        m = Module()

        m.submodules += [
            pll,
            rs,
        ]

        return m


class Top(Elaboratable):
    def elaborate(self, platform):
        # You apparently really needs the dir='-' thing
        clk_pin = platform.request(platform.default_clk, dir='-')

        led = platform.request('user_led', 0)

        m = Module()
        pll = PLL(12, 204)

        # Override default sync domain
        m.domains += pll.domain

        p1 = PulseStep(204000000)
        p2 = PulseStep(204000000)
        p3 = PulseStep(204000000)

        m.submodules += [p1, p2, p3]

        m.d.comb += [
            pll.clk_pin.eq(clk_pin),
            p1.input.eq(True),
            p1.trigger.eq(True),
            p2.input.eq(p1.output),
            p2.trigger.eq(p1.done),
            p3.input.eq(p2.output),
            p3.trigger.eq(p2.done),
            led.eq(p3.output),
        ]

        if platform is not None:
            pass

        return m


class PulserSim(Elaboratable):
    def __init__(self):
        self.start = Signal(reset=1)
        self.enable = Signal(reset=1)
        self.status = Signal()
        self.wat = Signal()

    def elaborate(self, platform):
        m = Module()

        p1 = PulseStep(5)
        p2 = PulseStep(5)
        p3 = PulseStep(5)

        m.submodules += [
            p1,
            p2,
            p3,
        ]

        m.d.combs += [
            p1.input.eq(self.start),
            p1.en.eq(self.enable),
            p2.input.eq(p1.output),
            p2.en.eq(p1.done),
            p3.input.eq(p2.output),
            p3.en.eq(p2.done),
            self.status.eq(p3.output),
            self.wat.eq(p3.done),
        ]

        return m


if __name__ == '__main__':
    #platform = ICEBreakerPlatform()
    #platform.build(Top(), do_program=True)

    dut = PulserSim()
    def bench():
        # Set starting values
        yield dut.enable.eq(1)
        yield dut.start.eq(1)
        yield Settle()

    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="sync")
    sim.add_sync_process(bench)
    with sim.write_vcd("pulser.vcd"):
        sim.run()

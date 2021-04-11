from collections import namedtuple
from nmigen import *
from nmigen.cli import main
from nmigen.lib.cdc import ResetSynchronizer
from nmigen.sim import *
from nmigen_boards.icestick import ICEStickPlatform
import warnings


class PulseStep(Elaboratable):
    """Chainable pulse step primitive.

    Parameters
    ----------
    duration : int
        Duration of pulse step

    Attributes
    ----------
    en: in
        Enable
    input: in
        Input state
    output: out
        Output state, buffered before countdown, inverted after
    done: out
        End status chainable to next input trigger

    Chaining
    --------
    ```
           +--------------------+     +--------------------+
    0  --> | input->[~]->output | --> | input->[~]->output | --> pulse_out
           |         ^          |     |         ^          |
           |  dur_0  |          |     |  dur_1  |          |
    1  --> | !{ctr}->?--> done  | --> | !{ctr}->?--> done  | --> _
           +--------------------+     +--------------------+
    ```
    Starting from an initial state 0, the state of pulse_out is toggled every
    dur_j cycles by subsequent chained PulseStep instances. The (j+1)st
    instance is started via the jth instance setting done to high when ctr = -1
    Chaining these allows a (nearly) arbitrary binary output pulse sequence,
    except that the initial delay is a minimum of 1 cycle.
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
        # where you can just monitor the MSB of a signed signal to check if
        # it is negative.

        # We can use a range() to set the signal's shape automatically
        ctr = Signal(range(-1, self.duration - 1), reset=(self.duration - 2))

        m = Module()

        # input ^ done inverts the output once done is hi
        m.d.comb += [
            self.output.eq(self.input ^ self.done),
        ]

        with m.If(self.en):
            # Finished counting
            with m.If(ctr[-1]):
                # Set done, toggling output
                with m.If(~(self.done)):
                    m.d.sync += [
                        # Indicate done
                        self.done.eq(1),
                    ]
            # Still counting
            with m.Else():
                m.d.sync += [
                    # Decrement counter
                    ctr.eq(ctr - 1),
                ]
        with m.Else():
            # Continuously reset if disabled
            m.d.sync += [
                ctr.eq(self.duration - 2),
                self.done.eq(0),
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

        rs = ResetSynchronizer(~pll_lock, domain=self.domain_name)

        m = Module()

        m.submodules += [
            pll,
            rs,
        ]

        return m


class Trigger(Elaboratable):
    """Monitor input for a hi streak meeting a threshold count to trigger on.

    Parameters
    ----------
    count: int
        Number of successive hi inputs to count as a trigger. Will trigger on
        count sequential cycles of hi input, allowing lo cycles if cancelled
        by corresponding extra hi cycles.
    block: int
        Period to hold the trigger output hi. Input events are ignored during
        this time.

    Attributes
    ----------
    input: in
        Signal to monitor for trigger event.
    output: out
        Signal to set hi for trigger events.

    Notes
    -----
    Trigger methodology allows for either a straight run of hi inputs, or a
    "one step backwards, one step forwards" extension if lo cycles occur.
    For example, if count = 5, this will trigger on 11111, but also 110111011.

    The output hi time and the block time are the same.
    """
    def __init__(self, count, block):
        self.count = count
        self.block = block
        self.input = Signal()
        self.output = Signal()

        self.ports = [
            self.input,
            self.output,
        ]

    def elaborate(self, platform):
        m = Module()

        count_max = self.count - 2
        ctr = Signal(range(-1, self.count - 1), reset=count_max)

        trig_max = self.block - 2
        trig_ctr = Signal(range(-1, self.block - 1), reset=trig_max)

        with m.If(~self.output):
            with m.If(self.input):
                with m.If(ctr[-1]):
                    # trigger event
                    self.output.eq(1)
                    ctr.eq(count_max)
                with m.Else():
                    # decrement while input hi
                    ctr.eq(ctr - 1)
            with m.Else():
                with m.If(ctr < count_max):
                    # increment to max while input lo
                    ctr.eq(ctr + 1)
        with m.Else():
            with m.If(trig_ctr[-1]):
                # trigger finished, allow new trigger
                self.output.eq(0)
                trig_ctr.eq(trig_max)
            with m.Else():
                # count down trigger
                trig_ctr.eq(trig_ctr - 1)

        return m


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
            t.input.eq(1),
            p1.input.eq(self.start),
            p1.en.eq(t.output),
            p2.input.eq(p1.output),
            p2.en.eq(p1.done),
            p3.input.eq(p2.output),
            p3.en.eq(p2.done),
            p4.input.eq(p3.output),
            p4.en.eq(p3.done),
            led.eq(p4.output),

            led1.eq(off),
            led2.eq(off),
            led3.eq(off),
        ]

        return m


if __name__ == '__main__':
    platform = ICEStickPlatform()
    platform.build(Top(), do_program=True)

    #dut = Top()
    #def bench():
    #    # Run a few cycles
    #    for _ in range(3):
    #        yield
    #    # Start the pulse event
    #    yield dut.enable.eq(1)

    #sim = Simulator(dut)
    #sim.add_clock(4.9e-9, domain="sync")
    #sim.add_sync_process(bench)
    #with sim.write_vcd("pulser.vcd"):
    #    sim.run_until(2e-7, run_passive=True)

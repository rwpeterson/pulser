from nmigen import *
from nmigen.cli import main
from nmigen.sim import *


class PulseStep(Elaboratable):
    """Chainable pulse step primitive.

    Parameters
    ----------
    duration : int
        Duration of pulse step (minimum 1)

    Attributes
    ----------
    en: in
        Enable
    input: in
        Input state
    prev: in
        Chained counter trigger input
    output: out
        Output state, buffered before countdown, inverted after
    next: out
        Chained counter trigger output

    Chaining
    --------
    ```
           +---------------------+     +---------------------+
    0  --> | input->[~]-->output | --> | input->[~]-->output | --> pulse_out
           |         ^           |     |          ^          |
           |         |           |     |          |          |
    1  --> | prev->{ctr0}?->next | --> | prev->{ctr1}?->next | --> _
           +---------------------+     +---------------------+
                     |                           |
    en --------------+---------------------------+
    ```
    Starting from an initial state 0, the state of pulse_out is toggled every
    dur_j cycles by subsequent chained PulseStep instances. ctr(j+1) is started
    when prev is high, controlled by the jth instance setting next to high when
    ctrj = -1. Chaining these allows a (nearly) arbitrary binary output pulse
    sequence, except that the initial delay is a minimum of 1 cycle. Using a
    global en in addition to prev and next ensures that resetting is
    instantaneous.
    """

    def __init__(self, duration):
        self.duration = duration + 1
        self.en = Signal()
        self.input = Signal()
        self.output = Signal()
        self.prev = Signal()
        self.next = Signal()

        self.ports = [
            self.en,
            self.input,
            self.output,
            self.prev,
            self.next,
        ]

    def elaborate(self, platform):
        # It seems cheap on FPGAs to only check one bit of a number instead of
        # some arbitrary value, so loops often count down and terminate at -1,
        # where you can just monitor the MSB of a signed signal to check if
        # it is negative.

        # We can use a range() to set the signal's shape automatically
        ctr = Signal(range(-1, self.duration - 1), reset=(self.duration - 2))

        m = Module()

        m.d.comb += [
            self.next.eq(ctr[-1]),
            self.output.eq((self.input) ^ ((self.en) & (self.next))),
        ]
        with m.If(self.prev):
            # Finished counting
            with m.If(~ctr[-1]):
                m.d.sync += [
                    # Decrement counter
                    ctr.eq(ctr - 1),
                ]
        with m.Else():
            # Continuously reset if disabled
            m.d.sync += [
                ctr.eq(self.duration - 2),
            ]

        return m


if __name__ == '__main__':
    class Top(Elaboratable):
        def __init__(self):
            self.init = Signal()
            self.enable = Signal()

        def elaborate(self, platform):
            m = Module()

            p1 = PulseStep(1)
            p2 = PulseStep(2)
            p3 = PulseStep(3)
            p4 = PulseStep(4)

            m.submodules += [
                p1,
                p2,
                p3,
                p4,
            ]

            m.d.comb += [
                p1.input.eq(self.init),
                p1.prev.eq(self.enable),
                p1.en.eq(self.enable),
                p2.input.eq(p1.output),
                p2.prev.eq(p1.next),
                p2.en.eq(self.enable),
                p3.input.eq(p2.output),
                p3.prev.eq(p2.next),
                p3.en.eq(self.enable),
                p4.input.eq(p3.output),
                p4.prev.eq(p3.next),
                p4.en.eq(self.enable),
            ]

            return m

    dut = Top()
    def bench():
        # Run a few cycles
        for _ in range(3):
            yield
        # Start the pulse event
        yield dut.enable.eq(1)
        # Wait until it's done, reset, and redo
        for _ in range(13):
            yield
        yield dut.enable.eq(0)
        for _ in range(9):
            yield
        yield dut.enable.eq(1)

    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="sync")
    sim.add_sync_process(bench)
    with sim.write_vcd("pulsestep.vcd"):
        sim.run_until(40e-6, run_passive=True)
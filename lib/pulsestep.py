from nmigen import *
from nmigen.cli import main
from nmigen.sim import *


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



if __name__ == '__main__':
    class Top(Elaboratable):
        def __init__(self):
            self.init = Signal()
            self.enable = Signal()

        def elaborate(self, platform):
            m = Module()

            p1 = PulseStep(1)
            p2 = PulseStep(3)
            p3 = PulseStep(5)
            p4 = PulseStep(2)

            m.submodules += [
                p1,
                p2,
                p3,
                p4,
            ]

            m.d.comb += [
                p1.input.eq(self.init),
                p1.en.eq(self.enable),
                p2.input.eq(p1.output),
                p2.en.eq(p1.done),
                p3.input.eq(p2.output),
                p3.en.eq(p2.done),
                p4.input.eq(p3.output),
                p4.en.eq(p3.done),
            ]

            return m

    dut = Top()
    def bench():
        # Run a few cycles
        for _ in range(3):
            yield
        # Start the pulse event
        yield dut.enable.eq(1)

    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="sync")
    sim.add_sync_process(bench)
    with sim.write_vcd("pulsestep.vcd"):
        sim.run_until(30e-6, run_passive=True)
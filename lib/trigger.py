from nmigen import *
from nmigen.cli import main
from nmigen.sim import *

class Trigger(Elaboratable):
    """Monitor input for a rising edge.

    Parameters
    ----------
    block: int
        Period to hold the trigger output high. Input events are ignored during
        this time.

    Attributes
    ----------
    trig_in: in
        Signal to monitor for trigger event.
    trigger: out
        Signal to set hi for trigger events.
    """
    def __init__(self, block):
        self.block = block
        self.trig_in = Signal()
        self.trigger = Signal()

        self.ports = [
            self.trig_in,
            self.trigger,
        ]

    def elaborate(self, platform):
        m = Module()

        state = Signal()
        cur = Signal()
        lst = Signal()

        trig_max = self.block - 2
        trig_ctr = Signal(range(-1, self.block - 1), reset=trig_max)

        # When not triggered, monitor input
        with m.If(~self.trigger):
            # Monitor current and last input states
            m.d.sync += [
                lst = cur,
                cur = self.trig_in,
            ]
            # Check for rising edge
            with m.If((cur & 1) & (lst & 0)):
                m.d.sync +=[
                    # trigger event
                    self.trigger.eq(1),
                ]
        # When triggered:
        with m.Else():
            with m.If(trig_ctr[-1]):
                # trigger finished, allow new trigger
                m.d.sync += [
                    self.trigger.eq(0),
                    trig_ctr.eq(trig_max),
                ]
            with m.Else():
                # count down trigger
                m.d.sync += [
                    trig_ctr.eq(trig_ctr - 1),
                ]

        return m


if __name__ == '__main__':
    class Top(Elaboratable):
        def __init__(self):
            self.enable = Signal()
            self.trig_mon = Signal()

            self.ports = [
                self.enable,
                self.trig_mon,
            ]

        def elaborate(self, platform):
            m = Module()

            t = Trigger(3)

            m.submodules += [
                t,
            ]

            m.d.comb += [
                t.trig_in.eq(self.enable),
                self.trig_mon.eq(t.trigger),
            ]

            return m

    dut = Top()
    def bench():
        # Run a few cycles
        for _ in range(3):
            yield
        # First trigger event, clean
        yield dut.enable.eq(1)
        for _ in range(3):
            yield
        # Waiting period
        yield dut.enable.eq(0)
        for _ in range(9):
            yield
        # Second trigger event, with noise
        yield dut.enable.eq(1)
        yield
        yield
        yield dut.enable.eq(0)
        yield
        yield dut.enable.eq(1)
        yield
        yield
        yield dut.enable.eq(0)
        yield

    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="sync")
    sim.add_sync_process(bench)
    with sim.write_vcd("trigger.vcd"):
        sim.run_until(40e-6, run_passive=True)
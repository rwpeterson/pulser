from nmigen import *
from nmigen.cli import main
from nmigen.sim import *

class Trigger(Elaboratable):
    """Monitor input for a hi streak meeting a threshold count to trigger on.

    Parameters
    ----------
    count: int
        Number of high inputs to count as a trigger event. Will trigger on
        count sequential cycles of high input, or any series of (count + M)
        cycles where (count + M / 2) are high.
    block: int
        Period to hold the trigger output high. Input events are ignored during
        this time.

    Attributes
    ----------
    trig_in: in
        Signal to monitor for trigger event.
    trigger: out
        Signal to set hi for trigger events.

    Notes
    -----
    Trigger's logic allows for either a straight run of high input cycles, or a
    "one step backwards, one step forwards" extension if low cycles occur.
    For example, if count = 5, this will trigger on 11111, but also 110111011,
    since each low cycle is balanced with an additional high cycle. Once
    triggered, trigger will be held high for block cycles regardless of input.
    """
    def __init__(self, count, block):
        self.count = count
        self.block = block
        self.trig_in = Signal()
        self.trigger = Signal()

        self.ports = [
            self.trig_in,
            self.trigger,
        ]

    def elaborate(self, platform):
        m = Module()

        count_max = self.count - 2
        ctr = Signal(range(-1, self.count - 1), reset=count_max)

        trig_max = self.block - 2
        trig_ctr = Signal(range(-1, self.block - 1), reset=trig_max)

        with m.If(~self.trigger):
            with m.If(self.trig_in):
                with m.If(ctr[-1]):
                    m.d.sync +=[
                        # trigger event
                        self.trigger.eq(1),
                        # reset ctr
                        ctr.eq(count_max),
                    ]
                with m.Else():
                    # count down for every high input
                    m.d.sync += [
                        ctr.eq(ctr - 1),
                    ]
            with m.Else():
                with m.If(ctr < count_max):
                    # count up for every low input
                    m.d.sync += [
                        ctr.eq(ctr + 1),
                    ]
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

            t = Trigger(3, 5)

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
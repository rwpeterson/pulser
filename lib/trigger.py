from nmigen import *
from nmigen.cli import main
from nmigen.sim import *

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

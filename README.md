# pulser

Pulse generator for the IceStick FPGA eval board designed using nmigen.

## Running

In general, you need the development version of [nmigen][n]. The easiest way
to get started is to use `pip3`.

Either install directly using `pip3`:

    pip3 install --user 'git+https://github.com/nmigen/nmigen.git#egg=nmigen'

Or clone the repo and build locally:

    git clone https://github.com/nmigen/nmigen
    cd nmigen
    pip3 install --user -e .

Make sure to update it periodically!

You will also need GTKWave if you want to view the generated `.vcd`
waveforms from the simulation test benches.

The libraries in `lib/` all have an example testbench that will be simulated
when you run them directly:

    python3 lib/pulsestep.py

This will write `pulsestep.vcd` to the current directory. This assumes that you
have yosys, nextpnr, and icestorm tools installed locally. If you are using the
[YoWASP][y] distribution of these tools, the binaries will be prepended with
`yowasp-`. To use these, environment variables need to be set. The included
`yowasp-run` script does this for you, so instead of typing

    YOSYS=yowasp-yosys NEXTPNR_ICE40=yowasp-nextpnr-ice40 ICEPACK=yowasp-icepack python3 lib/pulsestep.py

you can simply type

    yowasp-run lib/pulsestep.py

[n]: https://github.com/nmigen/nmigen
[y]: http://yowasp.org

## Modules

### `PulseStep(duration)`

This is a chained primitive to describe pulse transitions, toggling the state of
a signal after `duration` cycles have elapsed, and outputting a second chainable
signal to start the next PulseStep instance. A two-pulse output would have four
`PulseStep` instances, one to set the rising edge of the first pulse after
a minimum delay of one cycle from the initial trigger rising edge, a second to
set the falling edge of the first pulse, a third to set the rising edge of the
second pulse, and a fourth to set the falling edge of the second pulse.

#### Example
For the following example module `Top`:
```python
class Top(Elaboratable):
    def __init__(self):
        self.init = Signal()
        self.trg = Signal()
        self.out = Signal()

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
            p1.prev.eq(self.trg),
            p1.en.eq(self.trg),
            p2.input.eq(p1.output),
            p2.prev.eq(p1.next),
            p2.en.eq(self.trg),
            p3.input.eq(p2.output),
            p3.prev.eq(p2.next),
            p3.en.eq(self.trg),
            p4.input.eq(p3.output),
            p4.prev.eq(p3.next),
            p4.en.eq(self.trg),
            self.out.eq(p4.output),
        ]
        return m
```

We can write the following testbench

```python
dut = Top()
def bench():
    # Note: yield by itself steps through one clock cycle
    # Note: yield expr sets expr, but does not step through a clock cycle

    # Run a few cycles
    for _ in range(3):
        yield
    # Start the pulse event
    yield dut.trg.eq(1)
    # Wait until pulses are done
    for _ in range(13):
        yield
    # Reset
    yield dut.trg.eq(0)
    for _ in range(9):
        yield
    # Do it again
    yield dut.trg.eq(1)

sim = Simulator(dut)
sim.add_clock(1e-6, domain="sync")
sim.add_sync_process(bench)
with sim.write_vcd("pulsestep.vcd"):
    sim.run_until(40e-6, run_passive=True)
```

After running the simulation, `pulsestep.vcd` file looks something like this in
GTKWave:

```
clk ‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_‾_

trg ____‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾__________________‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾

out ______‾‾‾‾______‾‾‾‾‾‾‾‾__________________________‾‾‾‾______‾‾‾‾‾‾‾‾______
```

We see that the delays from the trigger rise to subsequent output
transitions are 1, 2, 3, and 4 cycles, and that it resets and runs a second
time. Great!

### `Trigger(block)`

This triggers on a rising edge of the input signal, holding the output trigger
high for `block` cycles, during which it ignores the input.

### `PLL(freq_in, freq_out)`

This wraps a verilog module like that produced by `icepll` to set the PLL. See
the full design example to see how to integrate it and use it as the default
clock domain.

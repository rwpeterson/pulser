# pulser

Pulse generator for the IceStick FPGA eval board designed using amaranth.

## Overview

`pulser` is a set of amaranth modules and a script to dynamically generate
gateware implementing the specified pulse sequence. The FPGA is reflashed
every time you want to change the sequence, which takes around ten seconds
from script execution to operation.

## Installing

### amaranth

We need to install [amaranth][a], which is a Python library. See the
[documentation][ad], but the simplest way to get it is with `pip`:

    pip3 install amaranth

### amaranth-boards

Board-specific platform information (like which pins are mapped to I/O,
LEDs, etc.) is contributed by the community and packaged as a separate
library, [amaranth-boards][ab].

    pip3 install amaranth-boards

### yosys

YOSYS is the open-source toolchain used to synthesize the design. It may
be packaged for your distribution (Check the version! See amaranth docs),
but the most foolproof way is to install via the [YoWASP][y] package.
It uses `pip` to install versions of the tools compiled to WebAssembly.
They will take longer to run the first time as they compile, and are slightly
slower than native builds, but are cross-platform and easy to get.

If you are using YoWASP, the binaries will be prepended with `yowasp-`.
For amaranth to find them, environment variables need to be set. Without
doing anything, you would need to type:

    YOSYS=yowasp-yosys NEXTPNR_ICE40=yowasp-nextpnr-ice40 ICEPACK=yowasp-icepack python3 -m pulser 1 1 1 1

You have three options (laziest first):

1. You can invoke `pulser` with the -y flag, which automatically sets them:

    python3 -m pulser -y 1 1 1 1

2. You can use the `yowasp-env` script on POSIX systems to set the envvars and `exec` into the next command:

    ./yowasp-env python3 -m pulser 1 1 1 1

   This is necessary for running the simulations, as they don't support `-y` (or any other flags):

    ./yowasp-env python3 pulser/lib/pulsestep.py

3. You can set these envvars in your shell's rc file

#### Yosys under Windows

YoWASP works perfectly well on Windows, and is the easiest way to
install yosys. However, it's missing the `iceprog` programmer that
actually programs the FPGA. You can use a different program to flash the
`.bin` file, or use the [fpga-binutils][f] package to provide `iceprog`.
Download the latest prebuilt binaries, extract the folder somewhere, and
add `C:\path\to\fpga-binutils-64\mingw64\bin` folder to your `PATH`
environment variable. You may also need to use the Zadig tool with the
IceStick plugged in to switch the driver from WinUSB to libusbK.

### gtkwave (simulation only)

You will also need GTKWave if you want to view the generated `.vcd`
waveforms from the simulation test benches. This is optional.

The libraries in `lib/` all have an example testbench that will be simulated
when you run them directly:

    python3 pulser/lib/pulsestep.py

This will write `pulsestep.vcd` to the current directory, which you can view
in gtkwave.

[a]: https://github.com/amaranth-lang/amaranth
[ab]: https://github.com/amaranth-lang/amaranth-boards
[ad]: https://amaranth-lang.org/docs/amaranth/latest/
[y]: http://yowasp.org
[f]: https://github.com/sylefeb/fpga-binutils

## Running the script

The easiest way to use `pulser` is to run it as a script, which you can do
without installing it just by being in the project directory:

    cd pulser
    python3 -m pulser -h

This will show the help text. To set the clock to 204 MHz and program a pulse
sequence with an initial delay of 1 cycle (the minimum possible), a 10 cycle
pulse length, then a break of 25 cycles, and finally a second pulse of 15
cycles, we specify the following. Let's assume for fun that we are using
YoWASP, so we pass the `-y` flag too:

    python3 -m pulse -f 204 -y 1 10 25 15

The script will create a `build` directory containing build artifacts,
and `pulser.bin`. This is what you want to flash the FPGA with. YoWASP
doesn't distribute `iceprog`, but a copy is in [fpga-binutils][f] (check
the prebuilt binaries). You can have the script automatically flash the FPGA
when it's done synthesizing by passing the `-u` flag.


## Modules

This is an under-the-hood look at the design. The pulser script is just one
design built out of these primitives, and it's easy to make your own.

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

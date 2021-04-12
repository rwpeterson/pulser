# pulser

Experimental pulse generator design using nmigen

## Running

In general, you need the development version of [nmigen][n].
Either:
```
git clone https://github.com/nmigen/nmigen
cd nmigen
pip3 install --user .
``` 
Or:
```
pip3 install --user 'git+https://github.com/nmigen/nmigen.git#egg=nmigen'
```

You will also need GTKWave to view the generated `.vcd` waveforms from the
simulation test benches.

The `yowasp-run` script is provided to set the appropriate environment variables
if you are using the [YoWASP][y] distribution of open-source
FPGA tools. If you have yosys, nextpnr, and project icestorm tools installed
locally, you can just run, e.g., `python3 lib/pulsestep.py` directly to simulate
the testbench for the PulseStep module.

[n]: https://github.com/nmigen/nmigen
[y]: http://yowasp.org
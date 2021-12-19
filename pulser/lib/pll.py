from amaranth import *
from amaranth.lib.cdc import ResetSynchronizer
from amaranth.cli import main
from amaranth.sim import *
from collections import namedtuple
import warnings
        
class PLL(Elaboratable):
    """Set the PLL to produce a higher-frequency clock.

    Currently, there is not a way to [express PLL primitives][i] directly in
    amaranth. We use Instance to instantiate a Verilog module directly--in this
    case the one produced by `icepll`.

    For reference, see the [Instance source][n], example implementations
    ([1][e1] and [2][e2]), and a [blog post] on adapting them to the ICEStick.

    [i]: https://github.com/amaranth-lang/amaranth/issues/425
    [n]: https://github.com/amaranth-lang/amaranth/blob/main/amaranth/hdl/ir.py
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

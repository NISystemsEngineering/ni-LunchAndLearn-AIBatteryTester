"""Minimal ctypes wrapper around the NI-DMM C driver (nidmm_64.dll).

Only the calls needed for DC/AC voltage and voltage-waveform measurements are
wrapped, so the applications run without the optional `nidmm` Python package.
"""
import ctypes as C
import os

DEFAULT_DLL = r"C:\Program Files\IVI Foundation\IVI\Bin\nidmm_64.dll"

NIDMM_VAL_DC_VOLTS = 1
NIDMM_VAL_AC_VOLTS = 2
NIDMM_VAL_WAVEFORM_VOLTAGE = 1003
NIDMM_VAL_AUTO_RANGE_ON = -1.0
NIDMM_VAL_TIME_LIMIT_AUTO = -1

ViSession = C.c_uint32
ViStatus = C.c_int32
ViInt32 = C.c_int32
ViReal64 = C.c_double
ViBoolean = C.c_uint16


class DmmError(RuntimeError):
    pass


class Dmm:
    def __init__(self, resource: str, reset: bool = True, dll_path: str = DEFAULT_DLL):
        if not os.path.exists(dll_path):
            raise DmmError(f"NI-DMM driver not found at {dll_path}")
        self._lib = C.WinDLL(dll_path)
        self._declare()
        self._vi = ViSession(0)
        self._check(self._lib.niDMM_init(resource.encode(), True, reset, C.byref(self._vi)))
        self.resource = resource

    def _declare(self):
        lib = self._lib
        lib.niDMM_init.argtypes = [C.c_char_p, ViBoolean, ViBoolean, C.POINTER(ViSession)]
        lib.niDMM_ConfigureMeasurementDigits.argtypes = [ViSession, ViInt32, ViReal64, ViReal64]
        lib.niDMM_Read.argtypes = [ViSession, ViInt32, C.POINTER(ViReal64)]
        lib.niDMM_ConfigureWaveformAcquisition.argtypes = [ViSession, ViInt32, ViReal64,
                                                           ViReal64, ViInt32]
        lib.niDMM_ReadWaveform.argtypes = [ViSession, ViInt32, ViInt32, C.POINTER(ViReal64),
                                           C.POINTER(ViInt32)]
        lib.niDMM_GetError.argtypes = [ViSession, C.POINTER(ViStatus), ViInt32, C.c_char_p]
        lib.niDMM_close.argtypes = [ViSession]
        for fn in ("niDMM_init", "niDMM_ConfigureMeasurementDigits", "niDMM_Read",
                   "niDMM_ConfigureWaveformAcquisition", "niDMM_ReadWaveform",
                   "niDMM_GetError", "niDMM_close"):
            getattr(lib, fn).restype = ViStatus

    def _check(self, status: int):
        # Negative status is an error; positive is a warning and is ignored.
        if status < 0:
            code = ViStatus()
            buf = C.create_string_buffer(2048)
            self._lib.niDMM_GetError(self._vi, C.byref(code), len(buf), buf)
            raise DmmError(f"NI-DMM error {status}: {buf.value.decode(errors='replace')}")

    def configure_dc_volts(self, range_v: float = 10.0, digits: float = 6.5):
        self._check(self._lib.niDMM_ConfigureMeasurementDigits(
            self._vi, NIDMM_VAL_DC_VOLTS, range_v, digits))

    def configure_ac_volts(self, range_v: float = NIDMM_VAL_AUTO_RANGE_ON, digits: float = 5.5):
        self._check(self._lib.niDMM_ConfigureMeasurementDigits(
            self._vi, NIDMM_VAL_AC_VOLTS, range_v, digits))

    def configure_waveform(self, range_v: float, rate_hz: float, points: int):
        """DC-coupled voltage waveform acquisition; read with read_waveform()."""
        self._check(self._lib.niDMM_ConfigureWaveformAcquisition(
            self._vi, NIDMM_VAL_WAVEFORM_VOLTAGE, range_v, rate_hz, points))

    def read(self, timeout_ms: int = NIDMM_VAL_TIME_LIMIT_AUTO) -> float:
        value = ViReal64()
        self._check(self._lib.niDMM_Read(self._vi, timeout_ms, C.byref(value)))
        return value.value

    def read_waveform(self, points: int, timeout_ms: int = NIDMM_VAL_TIME_LIMIT_AUTO) -> list[float]:
        buf = (ViReal64 * points)()
        got = ViInt32()
        self._check(self._lib.niDMM_ReadWaveform(self._vi, timeout_ms, points, buf, C.byref(got)))
        return buf[:got.value]

    def close(self):
        if self._vi.value:
            self._lib.niDMM_close(self._vi)
            self._vi = ViSession(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

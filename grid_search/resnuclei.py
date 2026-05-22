from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Optional


def fortran_read(f) -> Optional[bytes]:
    blen = f.read(4)
    if not blen:
        return None
    (size,) = struct.unpack("=i", blen)
    data = f.read(size)
    blen2 = f.read(4)
    if blen != blen2:
        raise IOError("Reading Fortran block")
    return data


def fortran_skip(f) -> int:
    blen = f.read(4)
    if not blen:
        return 0
    (size,) = struct.unpack("=i", blen)
    f.seek(size, 1)
    blen2 = f.read(4)
    if blen != blen2:
        raise IOError("Skipping Fortran block")
    return size


def unpack_array(data: bytes) -> tuple:
    return struct.unpack("=%df" % (len(data) // 4), data)


@dataclass
class Detector:
    num: int
    name: str
    volume: float = 0.0
    mhigh: int = 0
    zhigh: int = 0
    nmzmin: int = 0


class Resnuclei:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.title = ""
        self.time = ""
        self.weight = 0.0
        self.ncase = 0
        self.nbatch = 0
        self.detector: list[Detector] = []
        self.statpos = -1
        self.nisomers = 0
        self.evol = False
        self.tdecay: float = 0.0
        self._f = None
        self._read_header()

    def _open(self) -> None:
        self._f = open(self.filename, "rb")

    def _close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None

    def _read_base_header(self) -> None:
        data = fortran_read(self._f)
        if data is None:
            raise IOError("Invalid file")
        size = len(data)
        over1b = 0
        if size == 116:
            (title, time, self.weight) = struct.unpack("=80s32sf", data)
            self.ncase = 1
            self.nbatch = 1
        elif size == 120:
            (title, time, self.weight, self.ncase) = struct.unpack("=80s32sfi", data)
            self.nbatch = 1
        elif size == 124:
            (title, time, self.weight, self.ncase, self.nbatch) = struct.unpack("=80s32sfii", data)
        elif size == 128:
            (title, time, self.weight, self.ncase, over1b, self.nbatch) = struct.unpack("=80s32sfiii", data)
        else:
            raise IOError(f"Invalid USRxxx header size={size}")
        if over1b > 0:
            self.ncase = self.ncase + over1b * 1_000_000_000
        self.title = title.strip().decode(errors="replace")
        self.time = time.strip().decode(errors="replace")

    def _read_header(self) -> None:
        self._open()
        try:
            self._read_base_header()
            if self.ncase <= 0:
                self.evol = True
                self.ncase = -self.ncase
                data = fortran_read(self._f)
                if data is None:
                    raise IOError("Unexpected EOF reading evolution header")
                nir = (len(data) - 4) // 8
                struct.unpack("=i%df" % (2 * nir), data)
            else:
                self.evol = False

            for _ in range(1000):
                data = fortran_read(self._f)
                if data is None:
                    break
                size = len(data)
                if size == 14:
                    if data[:8] == b"ISOMERS:":
                        self.nisomers = struct.unpack("=10xi", data)[0]
                        fortran_read(self._f)
                        data = fortran_read(self._f)
                        if data is None:
                            raise IOError("Unexpected EOF reading ISOMERS header")
                        size = len(data)
                    if data[:10] == b"STATISTICS":
                        self.statpos = self._f.tell()
                        break
                elif size != 38:
                    raise IOError(f"Invalid RESNUCLEi header size={size}")

                header = struct.unpack("=i10siif3i", data)
                det = Detector(
                    num=header[0],
                    name=header[1].strip().decode(errors="replace"),
                    volume=header[4],
                    mhigh=header[5],
                    zhigh=header[6],
                    nmzmin=header[7],
                )
                self.detector.append(det)

                if self.evol:
                    data = fortran_read(self._f)
                    self.tdecay = struct.unpack("=f", data)[0]
                else:
                    self.tdecay = 0.0

                size = det.zhigh * det.mhigh * 4
                if size != fortran_skip(self._f):
                    raise IOError("Invalid RESNUCLEi file")
        finally:
            self._close()

    def read_data(self, n: int) -> Optional[bytes]:
        self._open()
        try:
            fortran_skip(self._f)
            if self.evol:
                fortran_skip(self._f)
            for _ in range(n):
                fortran_skip(self._f)
                if self.evol:
                    fortran_skip(self._f)
                fortran_skip(self._f)
                if self.nisomers:
                    fortran_skip(self._f)
                    fortran_skip(self._f)
            fortran_skip(self._f)
            if self.evol:
                fortran_skip(self._f)
            data = fortran_read(self._f)
            return data
        finally:
            self._close()

    def read_stat(self, n: int) -> Optional[tuple]:
        if self.statpos < 0:
            return None
        self._open()
        try:
            self._f.seek(self.statpos)
            nskip = 7 * n if self.nisomers else 6 * n
            for _ in range(nskip):
                fortran_skip(self._f)
            total = fortran_read(self._f)
            A = fortran_read(self._f)
            errA = fortran_read(self._f)
            Z = fortran_read(self._f)
            errZ = fortran_read(self._f)
            data = fortran_read(self._f)
            iso = fortran_read(self._f) if self.nisomers else None
            return (total, A, errA, Z, errZ, data, iso)
        finally:
            self._close()

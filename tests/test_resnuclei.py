import io
import struct
import pytest
from grid_search.resnuclei import fortran_read, fortran_skip, unpack_array, Detector


def make_block(payload: bytes) -> bytes:
    size = len(payload)
    header = struct.pack("=i", size)
    return header + payload + header


def test_fortran_read_returns_payload():
    payload = b"hello world!"
    f = io.BytesIO(make_block(payload))
    assert fortran_read(f) == payload


def test_fortran_read_eof_returns_none():
    f = io.BytesIO(b"")
    assert fortran_read(f) is None


def test_fortran_skip_skips_first_reads_second():
    block1 = make_block(b"first_block_")
    block2 = make_block(b"second_block")
    f = io.BytesIO(block1 + block2)
    size = fortran_skip(f)
    assert size == 12
    assert fortran_read(f) == b"second_block"


def test_unpack_array():
    data = struct.pack("=3f", 1.0, 2.0, 3.0)
    result = unpack_array(data)
    assert len(result) == 3
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(2.0)
    assert result[2] == pytest.approx(3.0)

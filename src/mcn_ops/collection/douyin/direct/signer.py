from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol
from urllib.parse import urlencode


class Signer(Protocol):
    def sign(self, params: Mapping[str, object], *, method: str = "GET") -> str: ...


_IV = (
    0x7380166F,
    0x4914B2B9,
    0x172442D7,
    0xDA8A0600,
    0xA96F30BC,
    0x163138AA,
    0xE38DEE4D,
    0xB0FB0E4E,
)
_ALPHABET = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"
_UA_ALPHABET = "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe"
_BROWSER_FINGERPRINT = "1920|1080|1920|1080|0|0|0|0|1920|1080|1920|1080|1920|1080|24|24|Win32"
_SORT_INDEX = (
    18, 20, 52, 26, 30, 34, 58, 38, 40, 53, 42, 21, 27, 54, 55, 31, 35, 57,
    39, 41, 43, 22, 28, 32, 60, 36, 23, 29, 33, 37, 44, 45, 59, 46, 47, 48,
    49, 50, 24, 25, 65, 66, 70, 71,
)
_XOR_INDEX = (
    18, 20, 26, 30, 34, 38, 40, 42, 21, 27, 31, 35, 39, 41, 43, 22, 28, 32,
    36, 23, 29, 33, 37, 44, 45, 46, 47, 48, 49, 50, 24, 25, 52, 53, 54, 55,
    57, 58, 59, 60, 65, 66, 70, 71,
)
_PERMUTATION = (
    121, 243, 55, 234, 103, 36, 47, 228, 30, 231, 106, 6, 115, 95, 78, 101,
    250, 207, 198, 50, 139, 227, 220, 105, 97, 143, 34, 28, 194, 215, 18, 100,
    159, 160, 43, 8, 169, 217, 180, 120, 247, 45, 90, 11, 27, 197, 46, 3, 84,
    72, 5, 68, 62, 56, 221, 75, 144, 79, 73, 161, 178, 81, 64, 187, 134, 117,
    186, 118, 16, 241, 130, 71, 89, 147, 122, 129, 65, 40, 88, 150, 110, 219,
    199, 255, 181, 254, 48, 4, 195, 248, 208, 32, 116, 167, 69, 201, 17, 124,
    125, 104, 96, 83, 80, 127, 236, 108, 154, 126, 204, 15, 20, 135, 112, 158,
    13, 1, 188, 164, 210, 237, 222, 98, 212, 77, 253, 42, 170, 202, 26, 22, 29,
    182, 251, 10, 173, 152, 58, 138, 54, 141, 185, 33, 157, 31, 252, 132, 233,
    235, 102, 196, 191, 223, 240, 148, 39, 123, 92, 82, 128, 109, 57, 24, 38,
    113, 209, 245, 2, 119, 153, 229, 189, 214, 230, 174, 232, 63, 52, 205, 86,
    140, 66, 175, 111, 171, 246, 133, 238, 193, 99, 60, 74, 91, 225, 51, 76,
    37, 145, 211, 166, 151, 213, 206, 0, 200, 244, 176, 218, 44, 184, 172, 49,
    216, 93, 168, 53, 21, 183, 41, 67, 85, 224, 155, 226, 242, 87, 177, 146,
    70, 190, 12, 162, 19, 137, 114, 25, 165, 163, 192, 23, 59, 9, 94, 179, 107,
    35, 7, 142, 131, 239, 203, 149, 136, 61, 249, 14, 156,
)


def _rotl(value: int, amount: int) -> int:
    amount %= 32
    return ((value << amount) | (value >> (32 - amount))) & 0xFFFFFFFF


def _sm3(data: bytes) -> bytes:
    bit_length = len(data) * 8
    padded = bytearray(data)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    padded.extend(bit_length.to_bytes(8, "big"))
    state = list(_IV)
    for offset in range(0, len(padded), 64):
        block = padded[offset : offset + 64]
        words = [int.from_bytes(block[index : index + 4], "big") for index in range(0, 64, 4)]
        for index in range(16, 68):
            value = words[index - 16] ^ words[index - 9] ^ _rotl(words[index - 3], 15)
            value = value ^ _rotl(value, 15) ^ _rotl(value, 23)
            words.append((value ^ _rotl(words[index - 13], 7) ^ words[index - 6]) & 0xFFFFFFFF)
        derived = [(words[index] ^ words[index + 4]) & 0xFFFFFFFF for index in range(64)]
        a, b, c, d, e, f, g, h = state
        for index in range(64):
            constant = 0x79CC4519 if index < 16 else 0x7A879D8A
            ss1 = _rotl((_rotl(a, 12) + e + _rotl(constant, index)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ _rotl(a, 12)
            ff = (a ^ b ^ c) if index < 16 else ((a & b) | (a & c) | (b & c))
            gg = (e ^ f ^ g) if index < 16 else ((e & f) | ((~e) & g))
            tt1 = (ff + d + ss2 + derived[index]) & 0xFFFFFFFF
            tt2 = (gg + h + ss1 + words[index]) & 0xFFFFFFFF
            d, c, b, a = c, _rotl(b, 9), a, tt1
            h, g, f = g, _rotl(f, 19), e
            e = (tt2 ^ _rotl(tt2, 9) ^ _rotl(tt2, 17)) & 0xFFFFFFFF
        state = [old ^ new for old, new in zip(state, (a, b, c, d, e, f, g, h))]
    return b"".join(value.to_bytes(4, "big") for value in state)


def _rc4(data: bytes, key: bytes) -> bytes:
    box = list(range(256))
    cursor = 0
    for index in range(256):
        cursor = (cursor + box[index] + key[index % len(key)]) % 256
        box[index], box[cursor] = box[cursor], box[index]
    left = right = 0
    output = bytearray()
    for value in data:
        left = (left + 1) % 256
        right = (right + box[left]) % 256
        box[left], box[right] = box[right], box[left]
        output.append(value ^ box[(box[left] + box[right]) % 256])
    return bytes(output)


def _custom_b64(data: bytes, alphabet: str, *, padding: bool = False) -> str:
    output: list[str] = []
    for offset in range(0, len(data), 3):
        chunk = data[offset : offset + 3]
        value = int.from_bytes(chunk.ljust(3, b"\0"), "big")
        count = 4 if len(chunk) == 3 else len(chunk) + 1
        output.extend(alphabet[(value >> shift) & 0x3F] for shift in (18, 12, 6, 0)[:count])
    if padding:
        output.extend("=" * ((4 - len(output) % 4) % 4))
    return "".join(output)


@dataclass
class ABogusSigner:
    """Generate Douyin Web ``a_bogus`` values without a remote signing API.

    The packing/permutation structure is adapted from the Apache-2.0 F2
    implementation; hashing is implemented locally to avoid another runtime
    dependency. See ``THIRD_PARTY_NOTICES.md``.
    """

    user_agent: str
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    random_source: random.Random = field(default_factory=random.Random)
    browser_fingerprint: str = _BROWSER_FINGERPRINT

    def sign(self, params: Mapping[str, object], *, method: str = "GET") -> str:
        if method.upper() != "GET":
            raise ValueError("the direct Douyin signer currently supports GET only")
        query = urlencode([(key, str(value)) for key, value in params.items()])
        query_hash = _sm3(_sm3((query + "cus").encode("utf-8")))
        body_hash = _sm3(_sm3(b"cus"))
        ua_cipher = _rc4(self.user_agent.encode("utf-8"), b"\x00\x01\x0e")
        ua_hash = _sm3(_custom_b64(ua_cipher, _UA_ALPHABET, padding=True).encode("ascii"))
        start = self.clock_ms()
        end = self.clock_ms()
        packed = self._pack(query_hash, body_hash, ua_hash, start, end)
        payload = self._random_bytes() + self._transform(packed)
        return _custom_b64(payload, _ALPHABET)

    def _pack(self, query_hash: bytes, body_hash: bytes, ua_hash: bytes, start: int, end: int) -> bytes:
        values: dict[int, int] = {8: 3, 18: 44, 66: 0, 69: 0, 70: 0, 71: 0}
        for position, shift in zip(range(20, 24), (24, 16, 8, 0)):
            values[position] = (start >> shift) & 255
        values[24] = (start >> 32) & 255
        values[25] = (start >> 40) & 255
        options = (0, 1, 14)
        for base, option in zip((26, 30, 34), options):
            values[base] = (option >> 24) & 255
            values[base + 1] = (option >> 16) & 255
            values[base + 2] = (option >> 8) & 255
            values[base + 3] = option & 255
        values.update({38: query_hash[21], 39: query_hash[22], 40: body_hash[21], 41: body_hash[22]})
        values.update({42: ua_hash[23], 43: ua_hash[24]})
        for position, shift in zip(range(44, 48), (24, 16, 8, 0)):
            values[position] = (end >> shift) & 255
        values.update({48: values[8], 49: (end >> 32) & 255, 50: (end >> 40) & 255})
        aid = 6383
        values.update({51: 0, 52: 0, 53: 0, 54: 0, 55: 0, 56: aid})
        values.update({57: aid & 255, 58: (aid >> 8) & 255, 59: (aid >> 16) & 255, 60: (aid >> 24) & 255})
        values[64] = values[65] = len(self.browser_fingerprint)
        checksum = values[_XOR_INDEX[0]]
        for index in _XOR_INDEX[1:]:
            checksum ^= values.get(index, 0)
        output = [values.get(index, 0) for index in _SORT_INDEX]
        output.extend(self.browser_fingerprint.encode("ascii"))
        output.append(checksum)
        return bytes(output)

    def _random_bytes(self) -> bytes:
        output = bytearray()
        for _ in range(3):
            value = int(self.random_source.random() * 10000)
            output.extend(
                (((value & 255) & 170) | 1, ((value & 255) & 85) | 2,
                 ((value >> 8) & 170) | 5, ((value >> 8) & 85) | 40)
            )
        return bytes(output)

    def _transform(self, data: bytes) -> bytes:
        permutation = list(_PERMUTATION)
        output = bytearray()
        index_b = permutation[1]
        initial = 0
        value_e = 0
        for index, value in enumerate(data):
            if index == 0:
                initial = permutation[index_b]
                summed = index_b + initial
                permutation[1] = initial
                permutation[index_b] = index_b
            else:
                summed = initial + value_e
            summed %= len(permutation)
            output.append(value ^ permutation[summed])
            cursor = (index + 2) % len(permutation)
            value_e = permutation[cursor]
            summed = (index_b + value_e) % len(permutation)
            initial = permutation[summed]
            permutation[summed] = permutation[cursor]
            permutation[cursor] = initial
            index_b = summed
        return bytes(output)

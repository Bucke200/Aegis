"""Perceptual image hashing with Pillow only.

Keeps the API image lean: pHash uses a separable DCT and dHash a horizontal
difference, both on a resized grayscale image. Embeddings are added separately
by the media worker (task 14.2).
"""

from __future__ import annotations

import math
from io import BytesIO

from PIL import Image, UnidentifiedImageError


class InvalidImageError(ValueError):
    """Raised when bytes are not a decodable image."""


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:0{len(bits) // 4}x}"


def _cosine_table(size: int) -> list[list[float]]:
    return [[math.cos(math.pi * (2 * x + 1) * u / (2 * size)) for u in range(size)] for x in range(size)]


def _dct_2d(pixels: list[float], size: int, cosine: list[list[float]]) -> list[float]:
    rows: list[list[float]] = []
    for row in range(size):
        values = pixels[row * size : (row + 1) * size]
        rows.append(
            [
                sum(values[x] * cosine[x][u] for x in range(size))
                * (math.sqrt(1 / size) if u == 0 else math.sqrt(2 / size))
                for u in range(size)
            ]
        )
    result = [0.0] * (size * size)
    for column in range(size):
        values = [rows[row][column] for row in range(size)]
        for u in range(size):
            result[u * size + column] = sum(values[y] * cosine[y][u] for y in range(size)) * (
                math.sqrt(1 / size) if u == 0 else math.sqrt(2 / size)
            )
    return result


def dhash(image: Image.Image, hash_size: int = 8) -> str:
    """Difference hash: compare horizontally adjacent pixels."""

    grayscale = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(grayscale.tobytes())
    bits: list[bool] = []
    for row in range(hash_size):
        for column in range(hash_size):
            offset = row * (hash_size + 1) + column
            bits.append(pixels[offset] > pixels[offset + 1])
    return _bits_to_hex(bits)


def phash(image: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> str:
    """Perceptual hash: DCT low-frequency threshold at the median."""

    size = hash_size * highfreq_factor
    grayscale = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = [float(value) for value in grayscale.tobytes()]
    coefficients = _dct_2d(pixels, size, _cosine_table(size))
    low: list[float] = []
    for row in range(hash_size):
        for column in range(hash_size):
            low.append(coefficients[row * size + column])
    median = sorted(low)[len(low) // 2]
    return _bits_to_hex([value > median for value in low])


def hash_image(data: bytes) -> tuple[str, str]:
    """Return ``(phash, dhash)`` for encoded image bytes."""

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return phash(image), dhash(image)
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError("could not decode image") from error

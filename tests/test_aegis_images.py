"""Unit tests for perceptual image hashing."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from aegis.common.images import InvalidImageError, hash_image


def _gradient(width: int = 64, height: int = 64) -> Image.Image:
    image = Image.new("L", (width, height))
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (x * 4 + y * 2) % 256
    return image


def _encode(image: Image.Image, fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _hamming(left: str, right: str) -> int:
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def test_hash_is_deterministic() -> None:
    data = _encode(_gradient())
    assert hash_image(data) == hash_image(data)


def test_hashes_are_stable_under_resize_and_reencode() -> None:
    image = _gradient()
    resized = image.resize((96, 96), Image.Resampling.LANCZOS)
    phash_a, dhash_a = hash_image(_encode(image))
    phash_b, dhash_b = hash_image(_encode(resized, "JPEG"))
    assert _hamming(dhash_a, dhash_b) <= 8
    assert _hamming(phash_a, phash_b) <= 8


def test_different_images_differ() -> None:
    gradient = _encode(_gradient())
    inverted = _encode(Image.eval(_gradient(), lambda value: 255 - value))
    assert hash_image(gradient) != hash_image(inverted)


def test_invalid_bytes_are_rejected() -> None:
    with pytest.raises(InvalidImageError, match="decode"):
        hash_image(b"not an image")

import unittest
from unittest.mock import patch

from audio_player.spectrogram_image import build_spectrogram_ppm, np


@unittest.skipIf(np is None, "NumPy is required for spectrogram rendering")
class SpectrogramImageTests(unittest.TestCase):
    def setUp(self):
        self.palette = [bytes((index, 255 - index, index % 17)) for index in range(256)]

    def pixels(self, values, width, height):
        image = build_spectrogram_ppm(values, self.palette, width, height)
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        self.assertTrue(image.startswith(header))
        self.assertEqual(len(image), len(header) + width * height * 3)
        return image[len(header):]

    def test_same_size_image_flips_frequency_rows_and_preserves_rgb_colors(self):
        values = np.array([[0, 1, 2], [3, 4, 255]], dtype=np.uint8)

        self.assertEqual(
            self.pixels(values, 3, 2),
            b"".join(self.palette[index] for index in (3, 4, 255, 0, 1, 2)),
        )

    def test_uneven_upscaling_and_downscaling_match_existing_pixel_mapping(self):
        values = np.array([[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 255]], dtype=np.uint8)
        for width, height in ((7, 5), (2, 2), (1, 1), (13, 11)):
            with self.subTest(width=width, height=height):
                expected = bytearray()
                for y in range(height):
                    row = values[2 - min(2, int(y * 3 / height))]
                    for x in range(width):
                        expected.extend(self.palette[int(row[min(3, int(x * 4 / width))])])
                self.assertEqual(self.pixels(values, width, height), bytes(expected))

    def test_single_source_pixel_fills_the_output(self):
        values = np.array([[255]], dtype=np.uint8)

        self.assertEqual(self.pixels(values, 5, 3), self.palette[255] * 15)

    def test_invalid_dimensions_are_rejected(self):
        values = np.array([[0]], dtype=np.uint8)
        for width, height in ((0, 1), (1, 0), (-1, 2), (2, -1), (1.5, 2)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    build_spectrogram_ppm(values, self.palette, width, height)

    def test_invalid_source_grids_are_rejected(self):
        for values in (
            np.empty((0, 2), dtype=np.uint8), np.empty((2, 0), dtype=np.uint8),
            np.array([1, 2], dtype=np.uint8), np.zeros((1, 1, 1), dtype=np.uint8),
            np.array([[-1]]), np.array([[256]]), np.array([[0.5]]),
        ):
            with self.subTest(shape=values.shape, dtype=values.dtype):
                with self.assertRaises(ValueError):
                    build_spectrogram_ppm(values, self.palette, 1, 1)

    def test_invalid_palette_is_rejected(self):
        values = np.array([[0]], dtype=np.uint8)
        for palette in (self.palette[:255], [b"xx"] * 256):
            with self.subTest(color_count=len(palette)):
                with self.assertRaises(ValueError):
                    build_spectrogram_ppm(values, palette, 1, 1)


class SpectrogramDependencyTests(unittest.TestCase):
    def test_missing_numpy_reports_a_render_error(self):
        with patch("audio_player.spectrogram_image.np", None):
            with self.assertRaisesRegex(ValueError, "NumPy"):
                build_spectrogram_ppm(None, None, 1, 1)


if __name__ == "__main__":
    unittest.main()

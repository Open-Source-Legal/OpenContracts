from django.test import SimpleTestCase

from opencontractserver.utils.pdf_token_matching import (
    select_tokens_in_region,
    union_bounds,
)


def _tok(x, y, w, h, text):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


class SelectTokensInRegionTests(SimpleTestCase):
    def test_selects_inside_skips_outside(self):
        page = {
            "page": {"index": 0},
            "tokens": [
                _tok(10, 10, 40, 12, "CHAPTER"),
                _tok(55, 10, 10, 12, "1"),
                _tok(10, 500, 40, 12, "footer"),
            ],
        }
        region = {"left": 8, "top": 8, "right": 70, "bottom": 24}
        self.assertEqual(
            select_tokens_in_region(page, region, overlap_threshold=0.5), [0, 1]
        )

    def test_skips_image_and_blank(self):
        page = {
            "page": {"index": 0},
            "tokens": [
                {
                    "x": 10,
                    "y": 10,
                    "width": 40,
                    "height": 12,
                    "text": "",
                    "is_image": True,
                },
                _tok(10, 10, 40, 12, "REAL"),
            ],
        }
        region = {"left": 8, "top": 8, "right": 55, "bottom": 24}
        self.assertEqual(
            select_tokens_in_region(page, region, overlap_threshold=0.5), [1]
        )

    def test_union_bounds(self):
        tokens = [_tok(10, 10, 40, 12, "A"), _tok(55, 10, 10, 12, "B")]
        self.assertEqual(
            union_bounds(tokens, [0, 1]),
            {"left": 10.0, "top": 10.0, "right": 65.0, "bottom": 22.0},
        )

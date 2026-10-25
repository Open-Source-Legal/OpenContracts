"""Tokenizer deserialization must work before containerized parsers can start."""

from unittest import TestCase

import spacy
from spacy.tokenizer import Tokenizer


class SpacyTokenizerSerializationTests(TestCase):
    def test_english_tokenizer_round_trip_preserves_offsets(self):
        nlp = spacy.blank("en")
        text = "We can't change the offsets in $1,234.56 or U.S. contracts."
        expected = [(token.text, token.idx) for token in nlp(text)]

        # Model loading restores the tokenizer into an initialized English
        # tokenizer. preshed 3.0.14 overflows while clearing its special cases.
        tokenizer = nlp.tokenizer
        assert isinstance(tokenizer, Tokenizer)
        tokenizer.from_bytes(tokenizer.to_bytes())

        self.assertEqual([(token.text, token.idx) for token in nlp(text)], expected)

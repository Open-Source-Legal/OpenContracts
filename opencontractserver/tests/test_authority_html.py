"""Tests for the dependency-free HTML/URL normalization helpers used by
authority-pack providers.

``opencontractserver.pipeline.base.authority_html`` has no Django or ORM
dependency (stdlib only: hashlib, re, dataclasses, html.parser, pathlib,
urllib.parse), so these tests use ``SimpleTestCase`` -- matching the
convention already used for other pure-logic authority modules such as
``test_authority_sources.py``.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from opencontractserver.pipeline.base.authority_html import (
    AuthorityLink,
    canonicalize_authority_url,
    extract_authority_links,
    extract_labeled_value,
    normalize_html_text,
    stable_source_slug,
    visible_html_text,
)


class NormalizeHtmlTextTests(SimpleTestCase):
    def test_collapses_internal_whitespace(self):
        self.assertEqual(normalize_html_text("  a   b\n\tc  "), "a b c")

    def test_empty_string_stays_empty(self):
        self.assertEqual(normalize_html_text(""), "")

    def test_whitespace_only_collapses_to_empty(self):
        self.assertEqual(normalize_html_text("   \n\t  "), "")

    def test_single_word_untouched(self):
        self.assertEqual(normalize_html_text("word"), "word")


class AuthorityLinkTests(SimpleTestCase):
    def _link(self, **attrs_kwargs) -> AuthorityLink:
        return AuthorityLink(
            url="https://example.com/",
            text="Example",
            raw_href="/example",
            attributes=tuple(attrs_kwargs.get("attributes", ())),
        )

    def test_attribute_found(self):
        link = self._link(attributes=(("class", "foo"), ("id", "bar")))
        self.assertEqual(link.attribute("id"), "bar")

    def test_attribute_lookup_is_case_insensitive_on_name(self):
        link = self._link(attributes=(("class", "foo"),))
        self.assertEqual(link.attribute("CLASS"), "foo")

    def test_attribute_missing_returns_none_by_default(self):
        link = self._link(attributes=())
        self.assertIsNone(link.attribute("missing"))

    def test_attribute_missing_returns_supplied_default(self):
        link = self._link(attributes=())
        self.assertEqual(link.attribute("missing", "fallback"), "fallback")

    def test_is_frozen(self):
        link = self._link()
        with self.assertRaises(Exception):
            link.url = "https://other.example.com/"  # type: ignore[misc]


class CanonicalizeAuthorityUrlTests(SimpleTestCase):
    def test_lowercases_scheme_and_host(self):
        self.assertEqual(
            canonicalize_authority_url("https://Example.COM/Path"),
            "https://example.com/Path",
        )

    def test_strips_utm_and_known_tracking_params_by_default(self):
        result = canonicalize_authority_url(
            "https://example.com/a?utm_source=x&b=2&fbclid=123"
        )
        self.assertEqual(result, "https://example.com/a?b=2")

    def test_strips_gclid(self):
        result = canonicalize_authority_url("https://example.com/a?keep=1&gclid=xyz")
        self.assertEqual(result, "https://example.com/a?keep=1")

    def test_drops_fragment_by_default(self):
        result = canonicalize_authority_url("https://example.com/path?b=2#frag")
        self.assertEqual(result, "https://example.com/path?b=2")

    def test_keep_fragment_true_preserves_fragment(self):
        result = canonicalize_authority_url(
            "https://example.com/path?b=2#frag", keep_fragment=True
        )
        self.assertEqual(result, "https://example.com/path?b=2#frag")

    def test_relative_url_resolved_against_base(self):
        result = canonicalize_authority_url(
            "/relative/path", base_url="https://example.com/base/"
        )
        self.assertEqual(result, "https://example.com/relative/path")

    def test_missing_path_defaults_to_slash(self):
        self.assertEqual(
            canonicalize_authority_url("https://example.com"),
            "https://example.com/",
        )

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(
            canonicalize_authority_url("  https://example.com/path  "),
            "https://example.com/path",
        )

    def test_empty_url_raises_value_error(self):
        with self.assertRaises(ValueError):
            canonicalize_authority_url("")

    def test_mailto_scheme_raises_value_error(self):
        with self.assertRaises(ValueError):
            canonicalize_authority_url("mailto:foo@bar.com")

    def test_javascript_scheme_raises_value_error(self):
        with self.assertRaises(ValueError):
            canonicalize_authority_url("javascript:void(0)")

    def test_non_http_scheme_raises_value_error(self):
        with self.assertRaises(ValueError):
            canonicalize_authority_url("ftp://example.com/file")

    def test_error_message_includes_original_url(self):
        with self.assertRaisesMessage(ValueError, "mailto:foo@bar.com"):
            canonicalize_authority_url("mailto:foo@bar.com")


class ExtractAuthorityLinksTests(SimpleTestCase):
    BASE = "https://example.com/base/"

    def test_relative_and_absolute_links_resolved(self):
        html = (
            '<a href="/doc1">First Doc</a>'
            '<a href="https://example.com/doc2?utm_campaign=x"> Second  Doc </a>'
        )
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(
            [(link.url, link.text) for link in links],
            [
                ("https://example.com/doc1", "First Doc"),
                ("https://example.com/doc2", "Second Doc"),
            ],
        )

    def test_duplicate_url_and_text_pairs_are_deduplicated(self):
        html = '<a href="/doc1">First Doc</a><a href="/doc1">First Doc</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(len(links), 1)

    def test_same_url_different_text_both_kept(self):
        html = '<a href="/a">Same</a><a href="/a?utm_x=1">Same</a><a href="/a">Different</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual([link.text for link in links], ["Same", "Different"])

    def test_mailto_and_javascript_links_are_skipped(self):
        html = (
            '<a href="mailto:foo@bar.com">Mail</a>'
            '<a href="javascript:void(0)">JS</a>'
            '<a href="/doc1">Kept</a>'
        )
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual([link.text for link in links], ["Kept"])

    def test_img_alt_used_as_label_when_no_text(self):
        html = '<a href="/img-link"><img src="x.png" alt="Alt Text"/></a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].text, "Alt Text")

    def test_img_outside_anchor_is_ignored(self):
        html = '<img src="x.png" alt="Orphan Alt"/><a href="/d">Doc</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual([link.text for link in links], ["Doc"])

    def test_aria_label_used_when_text_and_alt_absent(self):
        html = '<a href="/empty-label" aria-label="Aria Label"></a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(links[0].text, "Aria Label")

    def test_title_used_when_text_and_aria_label_absent(self):
        html = '<a href="/empty-label2" title="Title Label"></a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(links[0].text, "Title Label")

    def test_nested_anchor_is_finalized_separately(self):
        html = '<a href="/outer">Outer <a href="/inner">Inner</a> tail</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(
            [(link.url, link.text) for link in links],
            [
                ("https://example.com/outer", "Outer"),
                ("https://example.com/inner", "Inner"),
            ],
        )

    def test_unclosed_anchor_finalized_on_parser_close(self):
        html = '<a href="/unclosed">Trailing text'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].text, "Trailing text")

    def test_links_inside_script_style_noscript_svg_are_suppressed(self):
        html = (
            '<div>Visible <script>var a = "<a href=\\"/hidden\\">Hidden</a>";</script>'
            " text</div>"
            "<style>.a { color: red; }</style>"
            '<noscript><a href="/noscript-link">NoScript</a></noscript>'
            '<svg><a href="/svg-link">SvgLink</a></svg>'
        )
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(links, [])

    def test_valueless_href_attribute_treated_as_empty(self):
        html = "<a href>Text</a>"
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, self.BASE)

    def test_html_entities_decoded_in_link_text(self):
        html = '<a href="/e">Fish &amp; Chips</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(links[0].text, "Fish & Chips")

    def test_keep_fragments_true_preserves_fragment_in_url(self):
        html = '<a href="/x#section">X</a>'
        links = extract_authority_links(html, base_url=self.BASE, keep_fragments=True)
        self.assertEqual(links[0].url, "https://example.com/x#section")

    def test_keep_fragments_false_strips_fragment(self):
        html = '<a href="/x#section">X</a>'
        links = extract_authority_links(html, base_url=self.BASE, keep_fragments=False)
        self.assertEqual(links[0].url, "https://example.com/x")

    def test_no_links_returns_empty_list(self):
        self.assertEqual(
            extract_authority_links("<p>No links here</p>", base_url=self.BASE), []
        )

    def test_link_attributes_are_normalized_and_sorted(self):
        html = '<a HREF="/x" Class="link" Data-Foo="Bar">X</a>'
        links = extract_authority_links(html, base_url=self.BASE)
        self.assertEqual(
            links[0].attributes,
            (("class", "link"), ("data-foo", "Bar"), ("href", "/x")),
        )


class VisibleHtmlTextTests(SimpleTestCase):
    def test_strips_tags_and_joins_text(self):
        html = "<div>Hello <b>World</b></div>"
        self.assertEqual(visible_html_text(html), "Hello World")

    def test_block_tags_introduce_line_breaks(self):
        html = "<h1>Title</h1><p>Para one.</p><p>Para two.</p>"
        self.assertEqual(visible_html_text(html), "Title\n\nPara one.\n\nPara two.")

    def test_consecutive_blank_lines_collapse_to_one(self):
        html = "<p>One</p><br/><br/><br/><p>Two</p>"
        self.assertEqual(visible_html_text(html), "One\n\nTwo")

    def test_leading_and_trailing_whitespace_stripped(self):
        html = "<p>  Only line  </p>"
        self.assertEqual(visible_html_text(html), "Only line")

    def test_hidden_tags_excluded_from_visible_text(self):
        html = (
            "<div>Visible</div>"
            '<script>document.write("<div>Hidden Script</div>");</script>'
            "<style>.a { color: red; }</style>"
            "<noscript><div>Hidden NoScript</div></noscript>"
            "<svg><text>Hidden Svg</text></svg>"
        )
        self.assertEqual(visible_html_text(html), "Visible")

    def test_empty_html_returns_empty_string(self):
        self.assertEqual(visible_html_text(""), "")

    def test_carriage_returns_normalized(self):
        html = "<p>One</p>\r\n<p>Two</p>\r<p>Three</p>"
        result = visible_html_text(html)
        self.assertNotIn("\r", result)
        self.assertEqual(result, "One\n\nTwo\n\nThree")


class ExtractLabeledValueTests(SimpleTestCase):
    def test_label_colon_value_same_line(self):
        text = "Title: Some Doc\nOther: stuff"
        self.assertEqual(extract_labeled_value(text, "Title"), "Some Doc")

    def test_label_lookup_is_case_insensitive(self):
        text = "Status\nActive"
        self.assertEqual(extract_labeled_value(text, "status"), "Active")

    def test_label_alone_on_line_reads_next_nonblank_line(self):
        text = "Status\n\nActive"
        self.assertEqual(extract_labeled_value(text, "Status"), "Active")

    def test_label_with_trailing_colon_and_no_inline_value_reads_next_line(self):
        text = "Date:\n2024-01-01"
        self.assertEqual(extract_labeled_value(text, "Date"), "2024-01-01")

    def test_label_present_but_no_following_content_returns_none(self):
        text = "Status:\n\n"
        self.assertIsNone(extract_labeled_value(text, "Status"))

    def test_label_at_end_of_text_with_no_following_lines_returns_none(self):
        text = "Status:"
        self.assertIsNone(extract_labeled_value(text, "Status"))

    def test_label_not_found_returns_none(self):
        text = "Title: Some Doc"
        self.assertIsNone(extract_labeled_value(text, "Missing"))

    def test_whitespace_around_value_is_normalized(self):
        text = "Date:   2024-01-01  "
        self.assertEqual(extract_labeled_value(text, "Date"), "2024-01-01")

    def test_empty_text_returns_none(self):
        self.assertIsNone(extract_labeled_value("", "Title"))


class StableSourceSlugTests(SimpleTestCase):
    def test_basic_title_slugified(self):
        self.assertEqual(stable_source_slug("Hello World!!"), "hello-world")

    def test_surrounding_whitespace_and_case_normalized(self):
        self.assertEqual(stable_source_slug("  Some File.PDF  "), "some-file")

    def test_url_uses_filename_stem(self):
        self.assertEqual(
            stable_source_slug("https://example.com/path/to/My Document.pdf"),
            "my-document",
        )

    def test_url_with_trailing_slash_uses_last_segment(self):
        self.assertEqual(stable_source_slug("https://example.com/path/to/"), "to")

    def test_empty_value_falls_back_to_document(self):
        self.assertEqual(stable_source_slug(""), "document")

    def test_punctuation_only_falls_back_to_document(self):
        self.assertEqual(stable_source_slug("!!!"), "document")

    def test_short_slug_returned_unmodified(self):
        value = "a" * 96
        self.assertEqual(stable_source_slug(value, max_length=96), value)

    def test_slug_exactly_at_max_length_is_not_truncated(self):
        # len == max_length is the boundary of the `<=` check; must not hash.
        value = "b" * 50
        result = stable_source_slug(value, max_length=50)
        self.assertEqual(result, value)
        self.assertNotIn("-", result)

    def test_long_slug_truncated_with_stable_hash_suffix(self):
        value = "A" * 200
        result = stable_source_slug(value, max_length=20)
        self.assertEqual(len(result), 20)
        self.assertRegex(result, r"^a{7}-[0-9a-f]{12}$")

    def test_long_slug_hash_is_deterministic(self):
        value = "some very long document title " * 5
        first = stable_source_slug(value, max_length=30)
        second = stable_source_slug(value, max_length=30)
        self.assertEqual(first, second)

    def test_different_inputs_producing_same_truncated_prefix_differ_by_hash(self):
        value_a = "Identical Prefix " + "A" * 100
        value_b = "Identical Prefix " + "B" * 100
        slug_a = stable_source_slug(value_a, max_length=25)
        slug_b = stable_source_slug(value_b, max_length=25)
        self.assertNotEqual(slug_a, slug_b)

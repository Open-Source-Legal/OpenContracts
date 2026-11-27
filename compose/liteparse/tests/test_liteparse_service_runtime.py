"""Tests for the LiteParse service's config loading and model guard (pure Python)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from liteparse_service.runtime import (  # noqa: E402
    MODEL_NAME,
    ServiceConfig,
    load_config,
    parser_options,
    require_model,
)

_BASE_ENV = {"LITEPARSE_API_KEY": "k", "OCRIA_NANO_MODEL_VERSION": "1.0.0"}


def _model(name=MODEL_NAME, version="1.0.0", complete=True):
    return NS(
        name=name, version=version, complete=complete, path="/opt/m", size_bytes=1
    )


def test_load_config_defaults():
    assert load_config(_BASE_ENV) == ServiceConfig(
        api_key="k",
        pool_size=2,
        parse_timeout=1500.0,
        ocr_workers=4,
        max_pages=2000,
        max_upload_mb=200,
        model_version="1.0.0",
    )


def test_load_config_reads_overrides():
    env = {
        **_BASE_ENV,
        "LITEPARSE_POOL_SIZE": "3",
        "LITEPARSE_PARSE_TIMEOUT_SECONDS": "60",
        "LITEPARSE_OCR_WORKERS": "8",
        "LITEPARSE_MAX_PAGES": "10",
        "LITEPARSE_MAX_UPLOAD_MB": "5",
    }
    config = load_config(env)
    assert (config.pool_size, config.parse_timeout, config.ocr_workers) == (3, 60.0, 8)
    assert (config.max_pages, config.max_upload_mb) == (10, 5)


@pytest.mark.parametrize("value", ["", "   "])
def test_load_config_requires_api_key(value):
    with pytest.raises(ValueError, match="LITEPARSE_API_KEY"):
        load_config({**_BASE_ENV, "LITEPARSE_API_KEY": value})


def test_load_config_requires_model_version():
    env = dict(_BASE_ENV)
    del env["OCRIA_NANO_MODEL_VERSION"]
    with pytest.raises(ValueError, match="OCRIA_NANO_MODEL_VERSION"):
        load_config(env)


def test_load_config_rejects_non_int():
    with pytest.raises(ValueError, match="LITEPARSE_POOL_SIZE"):
        load_config({**_BASE_ENV, "LITEPARSE_POOL_SIZE": "x"})


def test_require_model_accepts_complete_matching():
    wanted = _model()
    assert (
        require_model([_model(name="other"), wanted], name=MODEL_NAME, version="1.0.0")
        is wanted
    )


def test_require_model_rejects_missing():
    with pytest.raises(RuntimeError, match="ocria-nano 1.0.0 is not installed"):
        require_model([], name=MODEL_NAME, version="1.0.0")


def test_require_model_rejects_incomplete():
    with pytest.raises(RuntimeError, match="rebuild the image"):
        require_model([_model(complete=False)], name=MODEL_NAME, version="1.0.0")


def test_require_model_rejects_version_mismatch():
    with pytest.raises(RuntimeError, match="ocria-nano 1.0.0"):
        require_model([_model(version="0.9.0")], name=MODEL_NAME, version="1.0.0")


def test_parser_options_pin_backend_and_tolerate_page_errors():
    options = parser_options(load_config({**_BASE_ENV, "LITEPARSE_MAX_PAGES": "7"}))
    assert options["ocr_backend"] == MODEL_NAME
    assert options["emit_word_boxes"] is True
    assert options["extract_blocks"] is True
    assert options["continue_on_page_error"] is True
    assert options["max_pages"] == 7
    assert options["pool_size"] == 2
    assert options["parse_timeout"] == 1500.0
    assert options["num_workers"] == 4

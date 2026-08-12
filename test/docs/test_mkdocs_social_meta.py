import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mkdocs_uses_social_meta_override() -> None:
    mkdocs_config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "custom_dir: docs/overrides" in mkdocs_config
    assert 'site_url: !ENV [CHILMAI_DOCS_SITE_URL, ""]' in mkdocs_config
    assert "pages.github.io" not in mkdocs_config


def test_social_meta_override_outputs_required_tags() -> None:
    override = (ROOT / "docs/overrides/main.html").read_text(encoding="utf-8")

    assert "{% extends \"base.html\" %}" in override
    assert "page.canonical_url or config.site_url or page.url" in override
    assert "ChilmAIは自治体の保育所利用調整業務における入所選考処理を支援するソフトウェアです" in override
    assert 'config.site_url.rstrip("/") ~ "/assets/ogp.png"' in override
    assert 'social_image = "/assets/ogp.png"' in override

    expected_tags = [
        'property="og:type"',
        'property="og:title"',
        'property="og:description"',
        'property="og:url"',
        'property="og:image"',
        'name="twitter:card"',
        'content="summary_large_image"',
    ]
    for tag in expected_tags:
        assert tag in override


def test_social_share_image_exists() -> None:
    image = ROOT / "docs/assets/ogp.png"
    assert image.is_file()

    image_bytes = image.read_bytes()
    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image_bytes) >= 24
    assert image_bytes[12:16] == b"IHDR"
    width, height = struct.unpack(">II", image_bytes[16:24])
    assert (width, height) == (1200, 630)


def test_docs_uses_branding_and_social_meta() -> None:
    mkdocs_config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    index = (ROOT / "docs/index.md").read_text(encoding="utf-8")

    assert "custom_dir: docs/overrides" in mkdocs_config
    assert "stylesheets/chilmai.css" in mkdocs_config
    assert "javascripts/chilmai-search.js" in mkdocs_config
    assert "assets/favicon.svg" in mkdocs_config
    assert "assets/logo_yoko_black.svg" in index
    assert "img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue" in index
    assert "img.shields.io/badge/license-Apache--2.0-blue" in index

    for path in [
        ROOT / "docs/overrides/main.html",
        ROOT / "docs/assets/ogp.png",
        ROOT / "docs/assets/favicon.svg",
        ROOT / "docs/assets/logo_yoko_black.svg",
        ROOT / "docs/javascripts/chilmai-search.js",
        ROOT / "docs/stylesheets/chilmai.css",
    ]:
        assert path.is_file()

    favicon = ROOT / "docs/assets/favicon.svg"
    assert favicon.read_text(encoding="utf-8").startswith("<svg")

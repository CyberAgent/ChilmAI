.PHONY: dev uv-bootstrap uv-sync uv-install-browser uv-run-api uv-test uv-test-cov uv-test-browser uv-docs-build uv-package install install-test install-format run-api test test-browser docs-build package clean

dev:
	uv sync --extra test --extra format --extra package
	uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8501 --reload

uv-bootstrap:
	./scripts/bootstrap_uv.sh

uv-sync:
	uv sync --extra test --extra format --extra package

uv-install-browser:
	uv run playwright install chromium

uv-run-api:
	uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8501

uv-test:
	uv run pytest test/ -m 'not (browser or binary)' -n auto

# CI と同じく python -m pytest で起動する（pytest 直接起動だと cwd が
# sys.path に入らず、examples を import するテストが失敗するため）
uv-test-cov:
	uv run python -m pytest test/ -m 'not (browser or binary)' -n auto --cov --cov-report=term-missing --cov-report=html

uv-test-browser:
	uv run pytest test/chilmai/browser -m browser -n 1

uv-docs-build:
	uv run --extra docs mkdocs build --strict

uv-package:
	uv run apps/packager.py

install:
	pip install -e .

install-test:
	pip install -e .[test]

install-format:
	pip install -e .[format]

run-api:
	python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8501

test:
	.venv/bin/python -m pytest test/ -m 'not (browser or binary)' -n auto

test-browser:
	.venv/bin/python -m pytest test/chilmai/browser -m browser -n 1

docs-build:
	.venv/bin/mkdocs build --strict

package:
	python apps/packager.py

clean:
	rm -rf build dist *.spec.bak

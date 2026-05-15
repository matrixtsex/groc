.PHONY: test verify package clean

PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests

verify:
	$(PYTHON) -m compileall -q groc tests
	$(PYTHON) -m unittest discover -s tests
	bash -n bin/groc bin/groc-bridge
	sh -n bin/install install.sh scripts/package-release.sh
	./bin/groc --version
	./bin/groc models --check --dry-run

package:
	scripts/package-release.sh "$${VERSION:-v0.1.0}"

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# The extensionless script is not found by globbing for *.py, so the paths are
# passed explicitly. Paths that do not exist yet are skipped. The prototypes are
# mock code outside the product and are not checked.
SOURCES := $(wildcard multiplexer-dashboard tests)

.PHONY: check format lint typecheck test e2e

check: format lint typecheck test

format:
	$(if $(SOURCES),ruff format $(SOURCES),@echo "format: no sources yet")

lint:
	$(if $(SOURCES),ruff check $(SOURCES),@echo "lint: no sources yet")

typecheck:
	$(if $(SOURCES),pyrefly check $(SOURCES),@echo "typecheck: no sources yet")

# The unit tests run on the oldest supported Python and on the current one.
test:
	python3 -m unittest discover -s tests
	uv run --no-project --python 3.9 python -m unittest discover -s tests

# End-to-end tests in real multiplexers, isolated from the user's own.
e2e:
	scripts/e2e.sh

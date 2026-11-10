# The extensionless script is not found by globbing for *.py, so the paths are
# passed explicitly. Paths that do not exist yet are skipped. The prototypes are
# mock code outside the product and are not checked.
SOURCES := $(wildcard multiplexer-dashboard tests)

.PHONY: check format lint typecheck

check: format lint typecheck

format:
	$(if $(SOURCES),ruff format $(SOURCES),@echo "format: no sources yet")

lint:
	$(if $(SOURCES),ruff check $(SOURCES),@echo "lint: no sources yet")

typecheck:
	$(if $(SOURCES),pyrefly check $(SOURCES),@echo "typecheck: no sources yet")

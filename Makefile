.DEFAULT_GOAL := help
UV ?= uv
RUN = $(UV) run --locked python -I
BUILD ?= latest
VOLUME ?= /Volumes/Music
CLANG_FORMAT ?= $(if $(LLVM_BIN),$(LLVM_BIN),/opt/homebrew/opt/llvm/bin)/clang-format
C_SOURCES := $(shell git ls-files 'patch/*.c' 'patch/*.h')

.PHONY: help setup doctor test dev preview flash check accept publish clean format format-check lint
help:
	@echo 'make setup                  Sync the uv environment (Python 3.15)'
	@echo 'make doctor                 Check inputs, toolchain and native emulator'
	@echo 'make test [TEST=albums]      Feature tests; no package or goldens; PERF=1 adds cost/stress checks'
	@echo 'make dev                    Build, test and package a fresh dev version'
	@echo 'make preview [BUILD=latest] Preview that dev build'
	@echo 'make flash [BUILD=latest]   Copy the tested dev package to the card'
	@echo 'make ota-serve [PORT=8765] Run the local Software Update server (the card file m1plus-update-url names it)'
	@echo 'make ota [BUILD=latest]     Push the tested dev package to that server; then Software Update on the device'
	@echo 'make check                  Full release + restore integration check'
	@echo 'make accept                 Integration-only golden acceptance'
	@echo 'make publish [PUBLISH=1]    Upload the golden package as a draft GitHub release named VERSION'
	@echo 'make clean                  Remove retained check scratch files/logs'
	@echo 'make format                 Format payload C and headers'
	@echo 'make format-check           Check payload formatting without edits'
	@echo 'make lint                   Ruff bug checks on the Python (test, dev and check run it first)'

setup:
	$(UV) sync --locked
doctor:
	$(RUN) tools/doctor.py
test: lint
	$(RUN) tools/check.py $(if $(TEST),--test "$(TEST)",--tests-only) $(if $(JOBS),--jobs "$(JOBS)") $(if $(PERF),--perf)
dev: lint
	$(RUN) tools/check.py --dev $(if $(JOBS),--jobs "$(JOBS)")
preview:
	$(RUN) tools/preview.py --build "$(BUILD)"
flash:
	$(RUN) tools/flash_sd.py --build "$(BUILD)" --volume "$(VOLUME)" $(if $(DRY_RUN),--dry-run)
ota-serve:
	$(RUN) tools/ota_server.py serve $(if $(PORT),--port "$(PORT)")
ota:
	$(RUN) tools/ota_server.py push --build "$(BUILD)" $(if $(PORT),--server "http://127.0.0.1:$(PORT)")
check: lint
	$(RUN) tools/check.py $(if $(JOBS),--jobs "$(JOBS)")
accept:
	$(RUN) tools/check.py --update $(if $(JOBS),--jobs "$(JOBS)")
publish:
	$(RUN) tools/publish.py $(if $(PUBLISH),--publish) $(if $(DRY_RUN),--dry-run)
clean:
	$(RUN) tools/check.py --clean
format:
	$(CLANG_FORMAT) -i $(C_SOURCES)
format-check:
	$(CLANG_FORMAT) --dry-run --Werror $(C_SOURCES)
lint:
	$(UV) run --locked ruff check

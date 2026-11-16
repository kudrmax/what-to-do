.PHONY: up down restart status logs update build uninstall app test test-macos help

# Shortcuts for `where-to-go <command>`, the app's own command line, which works the same on macOS, Linux and
# Windows (see README). The command line reads the optional .env of this copy itself; `make app` reads it
# here for the app's name and port.
-include .env
PORT ?= 18765
INSTANCE_ENV_NAME ?= prod
MENU_BAR_ICON ?= 0

CLI := .venv/bin/where-to-go
# Marks that the Python packages are installed; they are installed again when the lock file is newer,
# for example after switching to a new release by hand.
PY_DEPS_STAMP := .venv/.deps-installed

$(PY_DEPS_STAMP): uv.lock pyproject.toml
	@echo "Installing Python dependencies..."
	@uv sync --frozen --all-groups
	@touch $(PY_DEPS_STAMP)

##@ Run
up: $(PY_DEPS_STAMP)  ## Build the interface if its sources changed and start the app
	@$(CLI) up

down: $(PY_DEPS_STAMP)  ## Stop the app and everything it started
	@$(CLI) down

restart: $(PY_DEPS_STAMP)  ## Stop the app and start it again as it ran
	@$(CLI) restart

status: $(PY_DEPS_STAMP)  ## Whether the app runs, its address, version and data folder
	@$(CLI) status

logs: $(PY_DEPS_STAMP)  ## Logs of the app and of its updates in one stream
	@$(CLI) logs

update: $(PY_DEPS_STAMP)  ## Update to the latest release and restart the app
	@$(CLI) update

build: $(PY_DEPS_STAMP)  ## Build the interface if its sources changed
	@$(CLI) build

uninstall: $(PY_DEPS_STAMP)  ## Stop the app and remove it from this computer
	@$(CLI) uninstall

##@ Development
test: $(PY_DEPS_STAMP)  ## Backend and interface tests
	.venv/bin/pytest -q
	cd frontend && npm test

##@ macOS app
app: $(PY_DEPS_STAMP)  ## Build the .app for this copy into ~/Applications
	@macos/scripts/build-app.sh "$(CURDIR)" "$(PORT)" "$(INSTANCE_ENV_NAME)" "$(MENU_BAR_ICON)"

test-macos:  ## Tests of the macOS app
	swift test --package-path macos

##@ Other
help:  ## Show the commands
	@awk 'BEGIN {FS = ":.*##"} \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	  /^[a-zA-Z_-]+:.*##/ { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

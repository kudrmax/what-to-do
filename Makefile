.PHONY: up down logs app test test-macos update help _up _down _stop-update-status-server

# .env of this copy: PORT, INSTANCE_ENV_NAME, DATA_DIR, MENU_BAR_ICON.
# A missing .env is created from .env.example by the rule below, then make reads it.
-include .env
export

APP_PID := .pids/app.pid
APP_LOG := .logs/app.log
UPD_LOG := .logs/update.log
UPD_STATUS_PID := .pids/update_status.pid
COPY_LOCK := .pids/make.lock
# Ticks of 0.25 s: how long to wait for a port to be freed and for the app to open it.
PORT_WAIT_TICKS := 40
START_WAIT_TICKS := 240
# Marks that the Python packages are installed; `make up` installs them again when the
# lock file is newer, for example after switching to a new release.
PY_DEPS_STAMP := .venv/.deps-installed
PY_DEPS_FILES := uv.lock pyproject.toml

ifeq ($(INSTANCE_ENV_NAME),prod)
BANNER_COLOR := \033[1;32m
else
BANNER_COLOR := \033[1;33m
endif

# Empty DATA_DIR keeps the app's own default folder.
DATA_ARG = $(if $(DATA_DIR),--data "$(DATA_DIR)")

# The working folder of process $$pid: dev, prod and worktree processes have the same name.
PID_CWD = lsof -a -p $$pid -d cwd -Fn 2>/dev/null | sed -n 's/^n//p'

define kill_by_pid
	@if [ -f $(1) ]; then \
	    pid=$$(cat $(1)); \
	    if kill -0 $$pid 2>/dev/null; then kill $$pid; echo "Stopped $(2) (PID $$pid)"; fi; \
	    rm -f $(1); \
	fi
endef

# Stop whatever of this copy listens on port $(1) with $(2) in its arguments, and wait
# until it is gone. Other copies on the same port are left alone.
define kill_own_on_port
	@pids=""; \
	for pid in $$(lsof -ti :$(1) -sTCP:LISTEN 2>/dev/null); do \
	    [ "$$($(PID_CWD))" = "$(CURDIR)" ] || continue; \
	    ps -p $$pid -o args= 2>/dev/null | grep -q '$(2)' || continue; \
	    kill $$pid 2>/dev/null && pids="$$pids $$pid" && echo "Stopped $(2) on port $(1) (PID $$pid)"; \
	done; \
	for i in $$(seq 1 $(PORT_WAIT_TICKS)); do \
	    alive=""; for pid in $$pids; do kill -0 $$pid 2>/dev/null && alive="$$alive $$pid"; done; \
	    [ -z "$$alive" ] && break; sleep 0.25; \
	done; true
endef

# Another copy on the port would answer at our address while ours dies on bind.
define require_port_free
	@pid=$$(lsof -ti :$(1) -sTCP:LISTEN 2>/dev/null | head -1); \
	if [ -n "$$pid" ]; then \
	    echo "ERROR: port $(1) is held by PID $$pid from $$($(PID_CWD))"; \
	    echo "       $$(ps -p $$pid -o args= | cut -c1-100)"; \
	    echo "       Stop it in that copy or change PORT in .env."; \
	    exit 1; \
	fi
endef

define wait_started
	@pid=$$(cat $(APP_PID)); \
	for i in $$(seq 1 $(START_WAIT_TICKS)); do \
	    if ! kill -0 $$pid 2>/dev/null; then \
	        echo "ERROR: the app exited on start. Last lines of $(APP_LOG):"; \
	        tail -n 20 $(APP_LOG); rm -f $(APP_PID); exit 1; \
	    fi; \
	    if lsof -a -p $$pid -i :$(PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	        echo "app started on port $(PORT) (PID $$pid)"; exit 0; \
	    fi; \
	    sleep 0.25; \
	done; \
	echo "ERROR: the app (PID $$pid) did not open port $(PORT) in time, see $(APP_LOG)"; exit 1
endef

# The status server `make update` answers the page with while the app is down; it must be
# gone before the app takes the port. A killed update.sh not yet reaped is a zombie with
# another command, so only a process running the status server counts as alive.
define stop_update_status_server
	@if [ -f $(UPD_STATUS_PID) ]; then \
	    pid=$$(cat $(UPD_STATUS_PID)); \
	    alive() { ps -o command= -p $$pid 2>/dev/null | grep -q update_status_server; }; \
	    if alive; then \
	        kill $$pid; \
	        ticks=0; \
	        while alive && [ $$ticks -lt $(PORT_WAIT_TICKS) ]; do sleep 0.25; ticks=$$((ticks + 1)); done; \
	        if alive; then echo "ERROR: update status server (PID $$pid) did not stop" >&2; exit 1; fi; \
	    fi; \
	    rm -f $(UPD_STATUS_PID); \
	fi
endef

# up and down of one copy run one at a time: the macOS app runs make up on its own.
# shlock takes the lock over when its owner died.
define with_copy_lock
	@mkdir -p .pids; \
	until shlock -f $(COPY_LOCK) -p $$$$; do \
	    echo "Waiting for another make up/down in this copy (PID $$(cat $(COPY_LOCK) 2>/dev/null))..."; \
	    sleep 1; \
	done; \
	trap 'rm -f $(COPY_LOCK)' EXIT; \
	$(MAKE) --no-print-directory $(1)
endef

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example"

$(PY_DEPS_STAMP): $(PY_DEPS_FILES)
	@echo "Installing Python dependencies..."
	@uv sync --frozen --all-groups
	@touch $(PY_DEPS_STAMP)

##@ Run (reads .env)
up:  ## Build the interface and start the app
	$(call with_copy_lock,_up)

_up: $(PY_DEPS_STAMP)
	@cd frontend && ( [ node_modules/.package-lock.json -nt package-lock.json ] || { echo "Installing frontend dependencies..."; npm ci --no-audit --no-fund; } )
	@echo "Building the interface..."
	@cd frontend && VITE_INSTANCE_ENV_NAME=$(INSTANCE_ENV_NAME) npm run build
	@mkdir -p .pids .logs
	$(call kill_by_pid,$(APP_PID),app)
	$(call kill_own_on_port,$(PORT),where-to-go)
	$(call stop_update_status_server)
	$(call require_port_free,$(PORT))
	@.venv/bin/where-to-go --ui frontend/dist --port $(PORT) $(DATA_ARG) >> $(APP_LOG) 2>&1 & echo $$! > $(APP_PID)
	$(call wait_started)
	@printf "\n$(BANNER_COLOR)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
	@printf "  What To Do  [instance: %s]\n" "$(INSTANCE_ENV_NAME)"
	@printf "  → http://localhost:%s\n" "$(PORT)"
	@printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n\n"

down:  ## Stop the app
	$(call with_copy_lock,_down)

_down:
	$(call kill_by_pid,$(APP_PID),app)
	$(call kill_own_on_port,$(PORT),where-to-go)

# Without with_copy_lock: the script runs make down and make up, which take the lock.
UPDATE_MAKE := $(MAKE)
update:  ## Update to the latest release: git fetch, make down, git checkout <tag>, make up
	@MAKE="$(UPDATE_MAKE)" scripts/update.sh

_stop-update-status-server:
	$(call stop_update_status_server)

logs:  ## Logs of the app and of make update in one stream
	@trap 'kill 0' INT TERM; \
	tail -F $(APP_LOG) 2>/dev/null | sed -l 's/^/app    | /' & \
	tail -F $(UPD_LOG) 2>/dev/null | sed -l 's/^/update | /' & \
	wait

##@ Development
test: $(PY_DEPS_STAMP)  ## Backend and interface tests
	.venv/bin/pytest -q
	cd frontend && npm test

##@ macOS app
app:  ## Build the .app for this copy into ~/Applications
	@macos/scripts/build-app.sh "$(CURDIR)" "$(PORT)" "$(INSTANCE_ENV_NAME)" "$(MENU_BAR_ICON)"

test-macos:  ## Tests of the macOS app
	swift test --package-path macos

##@ Other
help:  ## Show the commands
	@awk 'BEGIN {FS = ":.*##"} \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	  /^[a-zA-Z_-]+:.*##/ { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

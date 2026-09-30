# Server operator commands (TASK-059H3, ADR-013). Thin wrappers over
# deploy/bin; every gate stays in those commands. Run from the verified,
# read-only source copy accepted by schatten-receive, never from the upload
# folder:
#
#   make -C /opt/apps/schatten-sources/<commit>/deploy <target>
#
# Receiving is not a target: run the installed /usr/local/bin/schatten-receive
# directly, because this copy does not exist before it. No target runs
# `down -v`, prunes, deletes volumes, runs down migrations, restores
# production, seeds or bootstraps; rollback, initialization and scheduler
# activation stay direct deploy/bin commands (docs/PRODUCTION-RUNBOOK.md).

SHELL := /bin/bash
.DEFAULT_GOAL := help

DEPLOY_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
SOURCE_DIR := $(patsubst %/,%,$(dir $(DEPLOY_DIR)))
BIN := $(DEPLOY_DIR)/bin

# Values reach the commands through the environment, never through the
# recipe text, so they cannot inject shell syntax.
export RELEASE APPROVAL SERVICE BACKUP KEY PASSPHRASE

# $(call require,VAR,usage) stops with a usage message when VAR is empty.
require = if [[ -z "$${$(1)}" ]]; then printf 'make: %s is required.\nUsage: make %s\n' '$(1)' '$(2)' >&2; exit 2; fi
# $(call absolute,VAR) stops when VAR is set but relative: make -C runs the
# recipes in this deploy folder, not in the operator's working directory.
absolute = if [[ -n "$${$(1)}" && "$${$(1)}" != /* ]]; then printf 'make: %s must be an absolute path (make -C runs in %s)\n' '$(1)' '$(DEPLOY_DIR)' >&2; exit 2; fi
# Deploy tooling must match the release: a release ID ends with the first 12
# characters of the commit it was built from, and this copy is named after its
# commit, so another commit's (or an unverified) copy is refused.
same_commit = commit="$$(basename '$(SOURCE_DIR)')"; \
	if [[ ! "$${commit}" =~ ^[0-9a-f]{40}$$ || "$${RELEASE}" != *-"$${commit:0:12}" ]]; then \
	  printf 'make: release %s was not built from this source copy (%s); run make from /opt/apps/schatten-sources/<its commit>/deploy\n' "$${RELEASE}" '$(SOURCE_DIR)' >&2; exit 2; \
	fi

.PHONY: help check audit build deploy first-install status ps logs stop start backup restore cleanup-dry-run

help:
	@printf '%s\n' \
		'Usage: make -C /opt/apps/schatten-sources/<commit>/deploy <target>' \
		'' \
		'Receive first with the installed receiver (not a make target):' \
		'  /usr/local/bin/schatten-receive <manifest-sha256>' \
		'' \
		'Host:' \
		'  check                               Read-only prerequisites (check-host)' \
		'  audit                               Read-only sanitized host audit (audit-host)' \
		'Release (needs a recorded human approval reference):' \
		'  build                               Build and freeze a release from this source copy' \
		'  deploy RELEASE=<id> APPROVAL=<ref>  Deploy a frozen release built from this copy' \
		'  first-install RELEASE=<id> APPROVAL=<ref>' \
		'                                      First install on a fresh database only' \
		'Current release:' \
		'  status                              Release pointers, backups, restore evidence, scheduler' \
		'  ps                                  Service containers and their state' \
		'  logs [SERVICE=<service>]            Recent service logs (last 200 lines each)' \
		'  stop                                Stop running services; keeps containers and volumes' \
		'  start                               Start the services stopped by stop' \
		'Backups and maintenance:' \
		'  backup                              Encrypted on-demand backup (prints BACKUP_ID=)' \
		'  restore BACKUP=<id> KEY=</abs/file> [PASSPHRASE=</abs/file>]' \
		'                                      Restore rehearsal in a disposable database (never production);' \
		'                                      KEY and PASSPHRASE must be absolute paths' \
		'  cleanup-dry-run                     List Docker cleanup candidates; removes nothing' \
		'' \
		'Direct commands only: rollback, initialize, verify-runtime-hardening,' \
		'--enable-scheduler, retire-release and docker-cleanup --apply.'

check:
	@'$(BIN)/check-host'

audit:
	@'$(BIN)/audit-host'

build:
	@'$(BIN)/build-release' --source '$(SOURCE_DIR)'

deploy:
	@$(call require,RELEASE,deploy RELEASE=<release-id> APPROVAL=<reference>); \
	$(call require,APPROVAL,deploy RELEASE=<release-id> APPROVAL=<reference>); \
	$(same_commit); \
	'$(BIN)/deploy-release' "$${RELEASE}" --approval "$${APPROVAL}"

first-install:
	@$(call require,RELEASE,first-install RELEASE=<release-id> APPROVAL=<reference>); \
	$(call require,APPROVAL,first-install RELEASE=<release-id> APPROVAL=<reference>); \
	$(same_commit); \
	'$(BIN)/deploy-release' "$${RELEASE}" --approval "$${APPROVAL}" --first-install

status:
	@'$(BIN)/ops-status'

ps:
	@'$(BIN)/service' ps

logs:
	@if [[ -n "$${SERVICE}" ]]; then '$(BIN)/service' logs "$${SERVICE}"; else '$(BIN)/service' logs; fi

stop:
	@'$(BIN)/service' stop

start:
	@'$(BIN)/service' start

backup:
	@'$(BIN)/backup-now' --reason manual

restore:
	@$(call require,BACKUP,restore BACKUP=<backup-id> KEY=<absolute key file> [PASSPHRASE=<absolute file>]); \
	$(call require,KEY,restore BACKUP=<backup-id> KEY=<absolute key file> [PASSPHRASE=<absolute file>]); \
	$(call absolute,KEY); \
	$(call absolute,PASSPHRASE); \
	if [[ -n "$${PASSPHRASE}" ]]; then \
	  '$(BIN)/restore-rehearsal' "$${BACKUP}" --private-key "$${KEY}" --passphrase-file "$${PASSPHRASE}"; \
	else \
	  '$(BIN)/restore-rehearsal' "$${BACKUP}" --private-key "$${KEY}"; \
	fi

cleanup-dry-run:
	@'$(BIN)/docker-cleanup' --dry-run

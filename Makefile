# Tasks for this repository: the workbench targets every repository in the
# organization gets (host/workbench.mk), used here straight from this clone.
#
# checkmake reads only the first physical line of a .PHONY declaration, so
# every .PHONY here is written on one line.
.PHONY: all help

# Bare `make` shows the target list rather than doing something surprising.
all: help

include host/workbench.mk

help:
	@printf '%s\n' 'Usage:' '  make <target>' ''
	@$(MAKE) --no-print-directory workbench-help

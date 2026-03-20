# target: all - Default target. Does nothing.
all:
	echo "Hello, this is make for tiny-rewards-tg"
	echo "Try 'make help' and search available options"

# target: help - List of options
help:
	egrep "^# target:" [Mm]akefile

# target: check - check flake8 and mypy
check:
	pytest; mypy services; mypy shared; mypy tests; flake8 services; flake8 shared; flake8 tests
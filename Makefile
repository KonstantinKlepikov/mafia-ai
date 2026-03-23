# target: all - Default target. Does nothing.
all:
	echo "Hello, this is make for tiny-rewards-tg"
	echo "Try 'make help' and search available options"

# target: help - List of options
help:
	egrep "^# target:" [Mm]akefile

# target: check - check flake8 and mypy
check:
	pytest; mypy src; mypy tests; flake8 src; flake8 tests
# daimonic — Background learners, intuition, inter-daimon communication
# (OSP: subprocesses/ + daimonic steps)
#
# Re-export whispers.py for backward compatibility — existing code does
# `import daimonic; daimonic.consume_all_whispers()` etc.
from daimonic.whispers import *  # noqa: F401,F403

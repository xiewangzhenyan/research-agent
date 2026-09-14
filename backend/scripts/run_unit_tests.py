"""Run pytest with application coverage, avoiding Python 3.12's import tracing trap.

jieba's generated probability table is a very large Python dictionary literal.
Loading it after Python 3.12 monitoring starts can stall test collection for
minutes. Warm only this third-party module before pytest-cov starts; application
modules are still imported and measured normally during collection.
"""

import sys


def main():
    if sys.version_info[:2] == (3, 12):
        import jieba  # noqa: F401

    import pytest

    return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

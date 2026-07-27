"""Enable ``python -m boukensha`` alongside the installed console script.

Both target the same loader entry point, so a checkout runs without installing
the console script (``python -m boukensha``), and the two paths never diverge.
"""

from .loader import main

if __name__ == "__main__":
    main()

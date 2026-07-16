"""PyInstaller entry point for the Fin CLI.

Mirrors the ``fin = fincli.__main__:main`` console script. PyInstaller freezes
this module as the program entry; it simply hands off to the real dispatcher.
"""

from fincli.__main__ import main

if __name__ == "__main__":
    main()

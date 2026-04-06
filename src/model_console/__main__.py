"""Entry point for `python -m model_console`. Delegates to cli.main()."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())

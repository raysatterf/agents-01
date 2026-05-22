#!/usr/bin/env python3
from pathlib import Path
import sys


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.build_doc_pdfs import main as build_main

    return build_main()


if __name__ == "__main__":
    raise SystemExit(main())

"""Správa z příkazové řádky.

uv run python -m svj.sprava otevri-obdobi 2025 2026
"""

import argparse

from sqlalchemy import select

from . import audit
from .db import Obdobi, sezeni


def otevri_obdobi(roky: list[int]) -> None:
    with sezeni()() as s:
        audit.kdo(s, "příkazová řádka")
        for rok in roky:
            o = s.scalar(select(Obdobi).where(Obdobi.rok == rok))
            if o is None:
                s.add(Obdobi(rok=rok, stav="otevrene"))
                print(f"Období {rok} je otevřené.")
            else:
                print(f"Období {rok} už existuje (stav {o.stav}).")
        s.commit()


def main() -> None:
    parser = argparse.ArgumentParser(prog="svj.sprava")
    prikazy = parser.add_subparsers(dest="prikaz", required=True)
    p = prikazy.add_parser("otevri-obdobi", help="založí účetní období pro dané roky")
    p.add_argument("roky", nargs="+", type=int)
    args = parser.parse_args()
    if args.prikaz == "otevri-obdobi":
        otevri_obdobi(args.roky)


if __name__ == "__main__":
    main()

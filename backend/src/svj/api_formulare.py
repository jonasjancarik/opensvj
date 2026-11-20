"""API pro rozepsané formuláře sdílené mezi členy výboru."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import ulozene
from .db import UlozenyFormular, sezeni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/formulare")


class Formular(BaseModel):
    obsah: dict[str, Any] | None
    verze: int  # 0 = zatím neuložený
    upravil: str | None
    jmeno: str | None
    upraveno: datetime | None


class Ulozeni(BaseModel):
    obsah: dict[str, Any]
    verze: int = Field(ge=0)


def _formular(f: UlozenyFormular | None) -> Formular:
    if f is None:
        return Formular(obsah=None, verze=0, upravil=None, jmeno=None, upraveno=None)
    return Formular(
        obsah=f.obsah, verze=f.verze, upravil=f.upravil, jmeno=f.jmeno, upraveno=f.upraveno
    )


@router.get("/{druh}/{klic}")
def nacti(druh: str, klic: str, _: Prihlaseny) -> Formular:
    with sezeni()() as s:
        try:
            return _formular(ulozene.nacti_formular(s, druh, klic))
        except ulozene.ChybaFormulare as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.put("/{druh}/{klic}")
def uloz(druh: str, klic: str, pozadavek: Ulozeni, uzivatel: Prihlaseny) -> Formular:
    if len(json.dumps(pozadavek.obsah, ensure_ascii=False)) > ulozene.MAX_VELIKOST:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Formulář je příliš velký.")
    with sezeni()() as s:
        try:
            f = ulozene.uloz_formular(s, druh, klic, pozadavek.obsah, pozadavek.verze, uzivatel)
        except ulozene.ChybaFormulare as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
        except ulozene.Konflikt as e:
            s.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "kod": "konflikt",
                    "aktualni": _formular(e.aktualni).model_dump(mode="json"),
                },
            ) from e
        vysledek = _formular(f)
        s.commit()
    return vysledek

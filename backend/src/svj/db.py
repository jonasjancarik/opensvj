"""Databázové modely účetního deníku.

Deník je jen pro připisování: zaúčtovaný zápis ani jeho řádky nejde změnit ani smazat
(hlídají to triggery v migraci). Vyrovnanost MD = D kontroluje odložený constraint trigger
při commitu transakce, takže ji nejde obejít ani přímým SQL.
"""

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .nastaveni import nastaveni


class Zaklad(DeclarativeBase):
    pass


class Obdobi(Zaklad):
    __tablename__ = "obdobi"
    rok: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    stav: Mapped[str] = mapped_column(String(16), default="otevrene")
    __table_args__ = (
        CheckConstraint("stav in ('otevrene', 'v_uzaverce', 'uzavrene')", name="stav_obdobi"),
    )


class Zapis(Zaklad):
    __tablename__ = "zapis"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rok: Mapped[int] = mapped_column(ForeignKey("obdobi.rok"))
    poradove_cislo: Mapped[int] = mapped_column(Integer)
    datum: Mapped[date] = mapped_column(Date)
    doklad: Mapped[str] = mapped_column(String(32))
    operace: Mapped[str] = mapped_column(String(64))
    popis: Mapped[str] = mapped_column(Text)
    opravuje_zapis: Mapped[int | None] = mapped_column(ForeignKey("zapis.id"), nullable=True)
    idempotencni_klic: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    zauctoval: Mapped[str] = mapped_column(String(128))
    vytvoreno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    radky: Mapped[list["RadekZapisu"]] = relationship(
        back_populates="zapis", order_by="RadekZapisu.id"
    )
    # Zápisy, které tenhle opravují (storno).
    opravy: Mapped[list["Zapis"]] = relationship("Zapis", viewonly=True)

    @property
    def stornovany(self) -> bool:
        return any(o.operace == "storno" for o in self.opravy)

    __table_args__ = (
        UniqueConstraint("rok", "poradove_cislo", name="poradove_cislo_v_roce"),
        CheckConstraint("extract(year from datum) = rok", name="datum_v_roce"),
    )


class RadekZapisu(Zaklad):
    __tablename__ = "radek_zapisu"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    zapis_id: Mapped[int] = mapped_column(ForeignKey("zapis.id"))
    strana: Mapped[str] = mapped_column(String(2))
    role: Mapped[str] = mapped_column(String(64))
    ucet: Mapped[str] = mapped_column(String(16))
    castka: Mapped[int] = mapped_column(BigInteger)  # haléře
    jednotka: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sluzba: Mapped[str | None] = mapped_column(String(32), nullable=True)
    protistrana: Mapped[str | None] = mapped_column(String(128), nullable=True)
    popis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Spojí závazek (faktura) s jeho úhradami, např. interní číslo faktury.
    parovaci_symbol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    zapis: Mapped[Zapis] = relationship(back_populates="radky")
    __table_args__ = (
        CheckConstraint("strana in ('md', 'd')", name="strana"),
        CheckConstraint("castka > 0", name="kladna_castka"),
    )


class Faktura(Zaklad):
    """Přijatá faktura. Zaúčtuje se hned při zadání; zruší se stornem jejího zápisu."""

    __tablename__ = "faktura"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    cislo: Mapped[str] = mapped_column(String(16), unique=True)  # interní, např. 2026001
    rok: Mapped[int] = mapped_column(Integer)
    dodavatel: Mapped[str] = mapped_column(String(128))
    ico: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ucet_dodavatele: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cislo_dodavatele: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vs: Mapped[str | None] = mapped_column(String(10), nullable=True)
    vystaveno: Mapped[date | None] = mapped_column(Date, nullable=True)
    duzp: Mapped[date] = mapped_column(Date)
    splatnost: Mapped[date] = mapped_column(Date)
    castka: Mapped[int] = mapped_column(BigInteger)
    druh: Mapped[str] = mapped_column(String(32))
    popis: Mapped[str] = mapped_column(Text, default="")
    rozhodnuti: Mapped[str | None] = mapped_column(String(200), nullable=True)
    zapis_id: Mapped[int] = mapped_column(ForeignKey("zapis.id"), unique=True)
    zadal: Mapped[str] = mapped_column(String(128))
    vytvoreno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    zapis: Mapped[Zapis] = relationship()


def engine(url: str | None = None):
    return create_engine(url or nastaveni().database_url, future=True)


def session_factory(url: str | None = None) -> sessionmaker:
    return sessionmaker(engine(url), expire_on_commit=False)


@lru_cache
def sezeni() -> sessionmaker:
    """Sdílená továrna na sezení pro aplikaci (jedno spojení do databáze na proces)."""
    return session_factory()


class BankovniUcet(Zaklad):
    __tablename__ = "bankovni_ucet"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cislo: Mapped[str] = mapped_column(String(32), unique=True)
    ucel: Mapped[str] = mapped_column(String(32), unique=True)
    vytvoreno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankovniVypis(Zaklad):
    """Kopie výpisu banky nebo přehledu pohybů. Nemění se (trigger v migraci 0002)."""

    __tablename__ = "bankovni_vypis"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ucet_id: Mapped[int] = mapped_column(ForeignKey("bankovni_ucet.id"))
    druh: Mapped[str] = mapped_column(String(8), default="vypis")  # vypis | export
    rok: Mapped[int] = mapped_column(Integer)
    # U přehledu pohybů (export) číslo, zůstatky a obraty chybí.
    cislo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datum: Mapped[date] = mapped_column(Date)
    datum_stareho_zustatku: Mapped[date | None] = mapped_column(Date, nullable=True)
    stary_zustatek: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    novy_zustatek: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    obraty_debet: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    obraty_kredit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    format: Mapped[str] = mapped_column(String(16))
    nazev_souboru: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    nahral: Mapped[str] = mapped_column(String(128))
    nahrano: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ucet: Mapped[BankovniUcet] = relationship()


class BankovniPohyb(Zaklad):
    """Pohyb z výpisu. Částka v haléřích: příjem kladně, výdaj záporně."""

    __tablename__ = "bankovni_pohyb"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vypis_id: Mapped[int] = mapped_column(ForeignKey("bankovni_vypis.id"))
    ucet_id: Mapped[int] = mapped_column(ForeignKey("bankovni_ucet.id"))
    poradi: Mapped[int] = mapped_column(Integer)
    klic: Mapped[str] = mapped_column(String(160))
    datum: Mapped[date] = mapped_column(Date)
    valuta: Mapped[date | None] = mapped_column(Date, nullable=True)
    castka: Mapped[int] = mapped_column(BigInteger)
    kod_uctovani: Mapped[str] = mapped_column(String(1))
    protiucet: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kod_banky: Mapped[str | None] = mapped_column(String(4), nullable=True)
    nazev: Mapped[str] = mapped_column(Text)
    vs: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ks: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ss: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zprava: Mapped[str] = mapped_column(Text)
    vypis: Mapped[BankovniVypis] = relationship()
    ucet: Mapped[BankovniUcet] = relationship()
    parovani_vse: Mapped[list["ParovaniPohybu"]] = relationship(
        back_populates="pohyb", order_by="ParovaniPohybu.id"
    )

    @property
    def parovani(self) -> "ParovaniPohybu | None":
        """Platné zaúčtování pohybu (dřívější mohla být stornovaná)."""
        return next((p for p in self.parovani_vse if not p.zapis.stornovany), None)

    @property
    def smer(self) -> str:
        return "prijem" if self.castka > 0 else "vydaj"


class ParovaniPohybu(Zaklad):
    __tablename__ = "parovani_pohybu"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    pohyb_id: Mapped[int] = mapped_column(ForeignKey("bankovni_pohyb.id"), index=True)
    zapis_id: Mapped[int] = mapped_column(ForeignKey("zapis.id"), unique=True)
    operace: Mapped[str] = mapped_column(String(64))
    vstupy: Mapped[dict] = mapped_column(JSONB)
    zauctoval: Mapped[str] = mapped_column(String(128))
    vytvoreno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    pohyb: Mapped[BankovniPohyb] = relationship(back_populates="parovani_vse")
    zapis: Mapped[Zapis] = relationship()


class PravidloParovani(Zaklad):
    """Naučené párování: platby z tohoto protiúčtu (nebo s tímto VS) účtuj takto."""

    __tablename__ = "pravidlo_parovani"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    smer: Mapped[str] = mapped_column(String(6))
    protiucet: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vs: Mapped[str | None] = mapped_column(String(10), nullable=True)
    operace: Mapped[str] = mapped_column(String(64))
    parametry: Mapped[dict] = mapped_column(JSONB)
    vytvoril: Mapped[str] = mapped_column(String(128))
    zmeneno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OdskrtnutiUzaverky(Zaklad):
    """Ruční odškrtnutí (nebo zrušení) bodu uzávěrky. Jen pro připisování; platí poslední."""

    __tablename__ = "odskrtnuti_uzaverky"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    rok: Mapped[int] = mapped_column(Integer)
    kod: Mapped[str] = mapped_column(String(64))
    hotovo: Mapped[bool] = mapped_column(Boolean)
    kdo: Mapped[str] = mapped_column(String(128))
    jmeno: Mapped[str] = mapped_column(String(128), default="")
    kdy: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Osoba(Zaklad):
    """Vlastník nebo spoluvlastník. Osobní údaje jdou opravit i smazat, deníku se netýkají."""

    __tablename__ = "osoba"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    jmeno: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str | None] = mapped_column(String(10), nullable=True)
    adresa: Mapped[str] = mapped_column(Text, default="")  # adresa pro doručování
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ucet: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Od kdy souhlasí s doručováním e-mailem; None = jen poštou.
    souhlas_email: Mapped[date | None] = mapped_column(Date, nullable=True)
    poznamka: Mapped[str] = mapped_column(Text, default="")
    upravil: Mapped[str] = mapped_column(String(128))
    upraveno: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Vlastnictvi(Zaklad):
    """Kdo jednotku vlastnil od–do. Spoluvlastníci a manželé jsou jedno vlastnictví."""

    __tablename__ = "vlastnictvi"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    jednotka: Mapped[str] = mapped_column(String(32))
    plati_od: Mapped[date] = mapped_column(Date)
    plati_do: Mapped[date | None] = mapped_column(Date, nullable=True)
    zdroj: Mapped[str] = mapped_column(Text, default="")
    upravil: Mapped[str] = mapped_column(String(128))
    upraveno: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    vlastnici: Mapped[list["VlastnikJednotky"]] = relationship(
        back_populates="vlastnictvi",
        order_by="VlastnikJednotky.poradi",
        cascade="all, delete-orphan",
    )


class VlastnikJednotky(Zaklad):
    __tablename__ = "vlastnictvi_osoba"
    vlastnictvi_id: Mapped[int] = mapped_column(
        ForeignKey("vlastnictvi.id", ondelete="CASCADE"), primary_key=True
    )
    osoba_id: Mapped[int] = mapped_column(ForeignKey("osoba.id"), primary_key=True)
    poradi: Mapped[int] = mapped_column(Integer)
    podil: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vlastnictvi: Mapped[Vlastnictvi] = relationship(back_populates="vlastnici")
    osoba: Mapped[Osoba] = relationship()


class UlozenyFormular(Zaklad):
    """Rozepsaný formulář sdílený mezi uživateli; verze brání přepsání cizí změny."""

    __tablename__ = "ulozeny_formular"
    druh: Mapped[str] = mapped_column(String(32), primary_key=True)
    klic: Mapped[str] = mapped_column(String(64), primary_key=True)
    obsah: Mapped[dict] = mapped_column(JSONB)
    verze: Mapped[int] = mapped_column(Integer)
    upravil: Mapped[str] = mapped_column(String(128))
    jmeno: Mapped[str] = mapped_column(String(128), default="")
    upraveno: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Meridlo(Zaklad):
    """Měřidlo jednotky, nebo domu (jednotka None), osazené od–do."""

    __tablename__ = "meridlo"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    jednotka: Mapped[str | None] = mapped_column(String(32), nullable=True)
    druh: Mapped[str] = mapped_column(String(32))
    vyrobni_cislo: Mapped[str] = mapped_column(String(64))
    umisteni: Mapped[str] = mapped_column(String(200), default="")
    osazeno_od: Mapped[date] = mapped_column(Date)
    odstraneno_do: Mapped[date | None] = mapped_column(Date, nullable=True)
    nahrazuje_id: Mapped[int | None] = mapped_column(ForeignKey("meridlo.id"), nullable=True)
    poznamka: Mapped[str] = mapped_column(Text, default="")
    upravil: Mapped[str] = mapped_column(String(128))
    upraveno: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    odecty: Mapped[list["Odecet"]] = relationship(
        back_populates="meridlo", order_by="Odecet.datum", cascade="all, delete-orphan"
    )


class Odecet(Zaklad):
    """Stav měřidla k datu."""

    __tablename__ = "odecet"
    __table_args__ = (UniqueConstraint("meridlo_id", "datum", name="odecet_jeden_za_den"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    meridlo_id: Mapped[int] = mapped_column(ForeignKey("meridlo.id", ondelete="CASCADE"))
    datum: Mapped[date] = mapped_column(Date)
    stav: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    zdroj: Mapped[str] = mapped_column(String(200), default="")
    upravil: Mapped[str] = mapped_column(String(128))
    upraveno: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    meridlo: Mapped[Meridlo] = relationship(back_populates="odecty")

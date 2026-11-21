"""Odesílání e-mailů přes SMTP. Při vývoji se e-maily místo odeslání uloží jako soubory .eml."""

import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from .nastaveni import nastaveni


class ChybaPosty(Exception):
    """Odesílání nefunguje celé (chybí nastavení, server nejde zastihnout)."""


class OdmitnutyPrijemce(Exception):
    """Server odmítl konkrétní adresu příjemce."""


@dataclass
class Priloha:
    nazev: str
    obsah: bytes
    typ: str = "text/html"


def nastaveno() -> bool:
    n = nastaveni()
    return bool(n.smtp_from and (n.smtp_host or n.mail_dir))


def odesli(jmeno: str, email: str, predmet: str, text: str, prilohy: list[Priloha] = ()) -> str:
    """Odešle zprávu a vrátí její Message-ID. Výjimka znamená, že zpráva neodešla."""
    n = nastaveni()
    if not nastaveno():
        raise ChybaPosty(
            "Odesílání e-mailů není nastavené. Správce aplikace musí doplnit SMTP_FROM a SMTP_HOST."
        )
    z = EmailMessage()
    z["From"] = n.smtp_from
    z["To"] = formataddr((jmeno, email))
    z["Subject"] = predmet
    z["Message-ID"] = make_msgid(domain=parseaddr(n.smtp_from)[1].partition("@")[2] or None)
    z.set_content(text)
    for p in prilohy:
        hlavni, _, vedlejsi = p.typ.partition("/")
        z.add_attachment(p.obsah, maintype=hlavni, subtype=vedlejsi, filename=p.nazev)

    if not n.smtp_host:
        n.mail_dir.mkdir(parents=True, exist_ok=True)
        cesta = n.mail_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}.eml"
        cesta.write_bytes(z.as_bytes())
        return z["Message-ID"]

    try:
        if n.smtp_tls == "ssl":
            spojeni = smtplib.SMTP_SSL(n.smtp_host, n.smtp_port, timeout=30)
        else:
            spojeni = smtplib.SMTP(n.smtp_host, n.smtp_port, timeout=30)
        with spojeni:
            if n.smtp_tls == "starttls":
                spojeni.starttls(context=ssl.create_default_context())
            if n.smtp_user:
                spojeni.login(n.smtp_user, n.smtp_password)
            odmitnuti = spojeni.send_message(z)
    except smtplib.SMTPRecipientsRefused as e:
        raise OdmitnutyPrijemce(_popis(e.recipients.get(email))) from e
    except (smtplib.SMTPException, OSError) as e:
        raise ChybaPosty(f"E-mail se nepodařilo odeslat: {e}") from e
    if email in odmitnuti:
        raise OdmitnutyPrijemce(_popis(odmitnuti[email]))
    return z["Message-ID"]


def _popis(odpoved: tuple[int, bytes] | None) -> str:
    if not odpoved:
        return "Server adresu odmítl."
    kod, zprava = odpoved
    return f"Server adresu odmítl ({kod} {zprava.decode(errors='replace')})."

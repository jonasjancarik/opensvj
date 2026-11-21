import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import nodemailer from "nodemailer";

/**
 * Odeslání přihlašovacího odkazu. Používá stejné nastavení jako rozesílání dokumentů
 * v backendu (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_TLS, SMTP_FROM).
 * Bez SMTP_HOST se e-mail při vývoji uloží jako soubor .eml do MAIL_DIR.
 *
 * Vypsání odkazu do konzole jde zapnout jen výslovně (AUTH_LINKS_TO_CONSOLE=1) a mimo
 * produkci: kdo vidí výstup služby, může se odkazem přihlásit.
 */
export async function posliOdkaz(email: string, url: string): Promise<void> {
  const od = process.env.SMTP_FROM;
  const host = process.env.SMTP_HOST;
  const slozka = process.env.MAIL_DIR;
  const zprava = {
    from: od,
    to: email,
    subject: "Přihlášení do OpenSVJ",
    text:
      "Dobrý den,\n\n" +
      "přihlásíte se klepnutím na tento odkaz:\n\n" +
      `${url}\n\n` +
      "Odkaz platí 15 minut a jde použít jen jednou. Pokud jste o přihlášení nežádali, " +
      "e-mail můžete smazat.\n",
  };

  if (od && host) {
    const tls = process.env.SMTP_TLS ?? "starttls";
    const prenos = nodemailer.createTransport({
      host,
      port: Number(process.env.SMTP_PORT ?? 587),
      secure: tls === "ssl",
      requireTLS: tls === "starttls",
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD ?? "" }
        : undefined,
    });
    await prenos.sendMail(zprava);
    return;
  }
  if (od && slozka) {
    const prenos = nodemailer.createTransport({ streamTransport: true, buffer: true });
    const { message } = await prenos.sendMail(zprava);
    await mkdir(slozka, { recursive: true });
    await writeFile(join(slozka, `${Date.now()}-prihlaseni.eml`), message as Buffer);
    return;
  }
  if (process.env.AUTH_LINKS_TO_CONSOLE === "1" && process.env.NODE_ENV !== "production") {
    console.log(`[auth] přihlašovací odkaz pro ${email}: ${url}`);
    return;
  }
  throw new Error("Odesílání e-mailů není nastavené (chybí SMTP_HOST a SMTP_FROM).");
}

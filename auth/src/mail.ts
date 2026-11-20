/**
 * Odeslání přihlašovacího odkazu. Skutečné odesílání (SMTP nebo Cloudflare Email) se doplní
 * před nasazením. Do té doby se odkaz vypíše do konzole, ale jen když je to výslovně zapnuté
 * (AUTH_LINKS_TO_CONSOLE=1): kdo vidí výstup služby, může se odkazem přihlásit, takže na
 * serveru to zapnuté být nesmí.
 */
export async function posliOdkaz(email: string, url: string): Promise<void> {
  if (process.env.AUTH_LINKS_TO_CONSOLE !== "1" || process.env.NODE_ENV === "production") {
    throw new Error("Odesílání e-mailů zatím není nastavené.");
  }
  console.log(`[auth] přihlašovací odkaz pro ${email}: ${url}`);
}

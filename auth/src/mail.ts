/**
 * Odeslání přihlašovacího odkazu. Ve vývoji se odkaz jen vypíše do konzole;
 * skutečné odesílání (SMTP nebo Cloudflare Email) se doplní před nasazením.
 */
export async function posliOdkaz(email: string, url: string): Promise<void> {
  if (process.env.NODE_ENV === "production") {
    throw new Error("Odesílání e-mailů zatím není nastavené.");
  }
  console.log(`[auth] přihlašovací odkaz pro ${email}: ${url}`);
}

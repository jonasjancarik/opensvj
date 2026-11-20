/**
 * Přihlašování pro OpenSVJ: jen odkazem e-mailem, jen pro povolené adresy.
 *
 * Better Auth drží identitu a session (schéma `auth`). Backend v Pythonu ověřuje krátkodobý
 * JWT veřejnými klíči z /api/auth/jwks. Role a oprávnění k podpisu jsou v databázi aplikace.
 */
import { betterAuth } from "better-auth";
import { jwt, magicLink } from "better-auth/plugins";
import pg from "pg";
import { posliOdkaz } from "./mail.js";

function povinne(nazev: string): string {
  const hodnota = process.env[nazev];
  if (!hodnota) throw new Error(`Chybí proměnná prostředí ${nazev}`);
  return hodnota;
}

/** Tajemství podepisuje přihlášení, takže vzorová nebo krátká hodnota nesmí projít. */
function tajemstvi(): string {
  const hodnota = povinne("BETTER_AUTH_SECRET");
  if (hodnota.length < 32 || hodnota.startsWith("change-me")) {
    throw new Error(
      "BETTER_AUTH_SECRET je vzorová nebo příliš krátká hodnota. Vygenerujte vlastní: openssl rand -base64 32",
    );
  }
  return hodnota;
}

const appUrl = povinne("APP_URL");
const povolene = new Set(
  (process.env.AUTH_ALLOWED_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean),
);

export function jePovoleny(email: string): boolean {
  return povolene.has(email.trim().toLowerCase());
}

const db = new pg.Pool({
  connectionString: povinne("AUTH_DATABASE_URL"),
  options: "-c search_path=auth",
});

/**
 * Ukončí přihlášení lidem, kteří už nejsou na seznamu povolených. Volá se při startu,
 * takže po úpravě AUTH_ALLOWED_EMAILS stačí službu restartovat.
 */
export async function odhlasNepovolene(): Promise<number> {
  const vysledek = await db.query(
    `DELETE FROM session WHERE "userId" IN
       (SELECT id FROM "user" WHERE NOT (lower(email) = ANY($1::text[])))`,
    [[...povolene]],
  );
  return vysledek.rowCount ?? 0;
}

export const auth = betterAuth({
  appName: "OpenSVJ",
  baseURL: povinne("BETTER_AUTH_URL"),
  secret: tajemstvi(),
  trustedOrigins: [appUrl, ...(process.env.AUTH_TRUSTED_ORIGINS ?? "").split(",").filter(Boolean)],
  database: db,
  emailAndPassword: { enabled: false },
  session: { expiresIn: 60 * 60 * 24 * 14, updateAge: 60 * 60 * 24 },
  databaseHooks: {
    user: {
      create: {
        before: async (user) => {
          if (!jePovoleny(user.email)) return false;
          return { data: { ...user, email: user.email.toLowerCase() } };
        },
      },
    },
  },
  plugins: [
    magicLink({
      expiresIn: 60 * 15,
      sendMagicLink: async ({ email, url }) => {
        // Nepovolené adrese odkaz neposíláme, ale navenek se chováme stejně,
        // aby nešlo zjišťovat, kdo v aplikaci má účet.
        if (!jePovoleny(email)) {
          console.warn(`[auth] odkaz pro nepovolenou adresu nebyl odeslán`);
          return;
        }
        await posliOdkaz(email, url);
      },
    }),
    jwt({
      jwks: { keyPairConfig: { alg: "EdDSA", crv: "Ed25519" } },
      jwt: { issuer: appUrl, audience: appUrl, expirationTime: "5m" },
    }),
  ],
});

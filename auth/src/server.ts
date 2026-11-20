import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { auth, odhlasNepovolene } from "./auth.js";

const app = new Hono();
app.get("/health", (c) => c.json({ ok: true }));
app.on(["GET", "POST"], "/api/auth/*", (c) => auth.handler(c.req.raw));

try {
  const pocet = await odhlasNepovolene();
  if (pocet) console.log(`[auth] ukončeno přihlášení mimo seznam povolených: ${pocet}`);
} catch (e) {
  // Před první migrací tabulky ještě nejsou.
  console.warn(`[auth] přihlášení mimo seznam povolených se nepodařilo zkontrolovat: ${e}`);
}

const port = Number(process.env.AUTH_PORT ?? 3010);
serve({ fetch: app.fetch, port, hostname: "0.0.0.0" }, (info) => {
  console.log(`[auth] běží na http://0.0.0.0:${info.port}`);
});

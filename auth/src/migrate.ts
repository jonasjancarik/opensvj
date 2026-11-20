import { getMigrations } from "better-auth/db/migration";
import { auth } from "./auth.js";

const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(auth.options);
console.log(`[auth] tabulky k vytvoření: ${toBeCreated.map((t) => t.table).join(", ") || "žádné"}`);
console.log(`[auth] sloupce k doplnění: ${toBeAdded.map((t) => t.table).join(", ") || "žádné"}`);
await runMigrations();
console.log("[auth] migrace hotová");
process.exit(0);

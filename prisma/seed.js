import pkg from "@prisma/client";
const { PrismaClient } = pkg;
import pg from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import * as dotenv from "dotenv";
dotenv.config();

const __dirname = dirname(fileURLToPath(import.meta.url));

const connectionString = process.env.DATABASE_URL.replace(/[?&]sslmode=[^&]*/g, '');
const pool = new pg.Pool({
  connectionString,
  ssl: { rejectUnauthorized: false },
});
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

function parseCSV(filePath) {
  const content = readFileSync(filePath, "utf-8");
  const lines = [];
  let current = "";
  let inQuotes = false;

  // Handle quoted fields that may contain commas/newlines
  for (const char of content) {
    if (char === '"') {
      inQuotes = !inQuotes;
      current += char;
    } else if (char === "\n" && !inQuotes) {
      if (current.trim()) lines.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  if (current.trim()) lines.push(current);

  const headers = splitCSVLine(lines[0]);
  return lines.slice(1).map(line => {
    const values = splitCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] || ""; });
    return row;
  });
}

function splitCSVLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (const char of line) {
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      result.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current);
  return result;
}

async function seed() {
  console.log("Seeding sales orders from CSV...\n");

  const csvPath = join(__dirname, "seed-data.csv");
  const rows = parseCSV(csvPath);
  console.log(`Read ${rows.length} records from seed-data.csv`);

  // Clear existing data
  await prisma.salesOrder.deleteMany();
  console.log("Cleared existing sales orders");

  // Map CSV rows to Prisma format
  const data = rows.map(row => ({
    orderNumber:     row.orderNumber,
    customerName:    row.customerName,
    customerEmail:   row.customerEmail,
    deliveryDate:    row.deliveryDate ? new Date(row.deliveryDate) : null,
    totalAmount:     parseFloat(row.totalAmount),
    currency:        row.currency,
    status:          row.status,
    shippingAddress: row.shippingAddress,
  }));

  // Insert in batches of 500 to avoid query size limits
  const BATCH_SIZE = 500;
  let inserted = 0;
  for (let i = 0; i < data.length; i += BATCH_SIZE) {
    const batch = data.slice(i, i + BATCH_SIZE);
    const result = await prisma.salesOrder.createMany({ data: batch });
    inserted += result.count;
    console.log(`  Batch ${Math.floor(i / BATCH_SIZE) + 1}: inserted ${result.count} records`);
  }

  console.log(`\nTotal inserted: ${inserted} sales orders`);

  // Quick summary
  const count = await prisma.salesOrder.count();
  const sample = await prisma.salesOrder.findMany({ take: 5, orderBy: { orderNumber: "asc" } });

  console.log(`\nVerification: ${count} records in database`);
  console.log("─".repeat(70));
  sample.forEach(order => {
    console.log(
      `${order.orderNumber}  |  ${order.customerName.padEnd(20)}  |  ${order.status.padEnd(10)}  |  ${order.currency} ${order.totalAmount}`
    );
  });
  console.log("... and more");
  console.log("─".repeat(70));
}

seed()
  .catch(err => {
    console.error("Seed failed:", err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
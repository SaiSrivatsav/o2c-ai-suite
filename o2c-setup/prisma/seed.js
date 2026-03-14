import pkg from "@prisma/client";
const { PrismaClient } = pkg;
import pg from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import * as dotenv from "dotenv";
import { resolve } from "path";
dotenv.config({ path: resolve(dirname(fileURLToPath(import.meta.url)), '../../.env') });

const __dirname = dirname(fileURLToPath(import.meta.url));
const csvDir = join(__dirname, "csv");

const connectionString = process.env.DATABASE_URL.replace(/[?&]sslmode=[^&]*/g, '');
const pool = new pg.Pool({
  connectionString,
  ssl: { rejectUnauthorized: false },
});
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

// ── CSV Parser ─────────────────────────────────────────────────
function parseCSV(filePath) {
  const content = readFileSync(filePath, "utf-8");
  const lines = [];
  let current = "";
  let inQuotes = false;
  for (const char of content) {
    if (char === '"') { inQuotes = !inQuotes; current += char; }
    else if (char === "\n" && !inQuotes) { if (current.trim()) lines.push(current); current = ""; }
    else { current += char; }
  }
  if (current.trim()) lines.push(current);
  const headers = splitCSVLine(lines[0]);
  return lines.slice(1).map(line => {
    const values = splitCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] ?? ""; });
    return row;
  });
}

function splitCSVLine(line) {
  const result = []; let current = ""; let inQuotes = false;
  for (const char of line) {
    if (char === '"') inQuotes = !inQuotes;
    else if (char === "," && !inQuotes) { result.push(current); current = ""; }
    else current += char;
  }
  result.push(current);
  return result;
}

// ── Batch inserter ─────────────────────────────────────────────
async function batchInsert(modelName, data, batchSize = 500) {
  let inserted = 0;
  for (let i = 0; i < data.length; i += batchSize) {
    const batch = data.slice(i, i + batchSize);
    const result = await prisma[modelName].createMany({ data: batch });
    inserted += result.count;
  }
  return inserted;
}

// ── Type coercers per table ────────────────────────────────────
function toCustomer(r) {
  return {
    id: r.id, customerNumber: r.customerNumber, name: r.name, email: r.email, phone: r.phone,
    address: r.address, city: r.city, state: r.state || null, postalCode: r.postalCode,
    country: r.country, creditLimit: parseFloat(r.creditLimit), paymentTerms: r.paymentTerms,
    customerGroup: r.customerGroup, isActive: r.isActive === "true",
  };
}

function toMaterial(r) {
  return {
    id: r.id, materialNumber: r.materialNumber, description: r.description,
    materialGroup: r.materialGroup, unitOfMeasure: r.unitOfMeasure,
    weight: r.weight ? parseFloat(r.weight) : null, weightUnit: r.weightUnit,
    basePrice: parseFloat(r.basePrice), currency: r.currency, isActive: r.isActive === "true",
  };
}

function toSalesOrder(r) {
  return {
    id: r.id, orderNumber: r.orderNumber, customerId: r.customerId,
    orderDate: new Date(r.orderDate),
    requestedDeliveryDate: r.requestedDeliveryDate ? new Date(r.requestedDeliveryDate) : null,
    salesOrg: r.salesOrg, distributionChannel: r.distributionChannel, division: r.division,
    totalNetAmount: parseFloat(r.totalNetAmount), totalTaxAmount: parseFloat(r.totalTaxAmount),
    totalGrossAmount: parseFloat(r.totalGrossAmount), currency: r.currency,
    status: r.status, paymentTerms: r.paymentTerms,
  };
}

function toSalesOrderItem(r) {
  return {
    id: r.id, salesOrderId: r.salesOrderId, itemNumber: parseInt(r.itemNumber),
    materialId: r.materialId, description: r.description,
    quantity: parseFloat(r.quantity), unitOfMeasure: r.unitOfMeasure,
    unitPrice: parseFloat(r.unitPrice), netAmount: parseFloat(r.netAmount),
    taxAmount: parseFloat(r.taxAmount), currency: r.currency, status: r.status,
  };
}

function toSalesPartner(r) {
  return {
    id: r.id, salesOrderId: r.salesOrderId, customerId: r.customerId,
    partnerFunction: r.partnerFunction,
  };
}

function toPricingCondition(r) {
  return {
    id: r.id, salesOrderItemId: r.salesOrderItemId, conditionType: r.conditionType,
    conditionValue: parseFloat(r.conditionValue), currency: r.currency,
    isPercentage: r.isPercentage === "true", conditionBase: parseFloat(r.conditionBase),
    conditionAmount: parseFloat(r.conditionAmount),
  };
}

function toDelivery(r) {
  return {
    id: r.id, deliveryNumber: r.deliveryNumber, salesOrderId: r.salesOrderId,
    deliveryDate: new Date(r.deliveryDate), shippingPoint: r.shippingPoint,
    shippingAddress: r.shippingAddress, trackingNumber: r.trackingNumber || null,
    carrier: r.carrier || null, status: r.status,
    totalWeight: r.totalWeight ? parseFloat(r.totalWeight) : null, weightUnit: r.weightUnit,
  };
}

function toDeliveryItem(r) {
  return {
    id: r.id, deliveryId: r.deliveryId, salesOrderItemId: r.salesOrderItemId,
    itemNumber: parseInt(r.itemNumber), materialId: r.materialId,
    deliveredQuantity: parseFloat(r.deliveredQuantity), unitOfMeasure: r.unitOfMeasure,
    batchNumber: r.batchNumber || null,
  };
}

function toInvoice(r) {
  return {
    id: r.id, invoiceNumber: r.invoiceNumber, salesOrderId: r.salesOrderId,
    deliveryId: r.deliveryId, customerId: r.customerId,
    invoiceDate: new Date(r.invoiceDate), dueDate: new Date(r.dueDate),
    totalNetAmount: parseFloat(r.totalNetAmount), totalTaxAmount: parseFloat(r.totalTaxAmount),
    totalGrossAmount: parseFloat(r.totalGrossAmount), currency: r.currency, status: r.status,
  };
}

function toInvoiceItem(r) {
  return {
    id: r.id, invoiceId: r.invoiceId, salesOrderItemId: r.salesOrderItemId,
    deliveryItemId: r.deliveryItemId, materialId: r.materialId,
    itemNumber: parseInt(r.itemNumber), quantity: parseFloat(r.quantity),
    unitPrice: parseFloat(r.unitPrice), netAmount: parseFloat(r.netAmount),
    taxAmount: parseFloat(r.taxAmount), currency: r.currency,
  };
}

function toPayment(r) {
  return {
    id: r.id, paymentNumber: r.paymentNumber, invoiceId: r.invoiceId,
    customerId: r.customerId, paymentDate: new Date(r.paymentDate),
    amount: parseFloat(r.amount), currency: r.currency,
    paymentMethod: r.paymentMethod, referenceNumber: r.referenceNumber, status: r.status,
  };
}

function toCreditMemo(r) {
  return {
    id: r.id, creditMemoNumber: r.creditMemoNumber, invoiceId: r.invoiceId,
    salesOrderId: r.salesOrderId, customerId: r.customerId,
    creditDate: new Date(r.creditDate), reason: r.reason,
    totalAmount: parseFloat(r.totalAmount), currency: r.currency, status: r.status,
  };
}

// ── Seed pipeline (order matters for FK constraints) ───────────
const pipeline = [
  { file: "01_customers.csv",          model: "customer",          convert: toCustomer },
  { file: "02_materials.csv",          model: "material",          convert: toMaterial },
  { file: "03_sales_orders.csv",       model: "salesOrder",        convert: toSalesOrder },
  { file: "04_sales_order_items.csv",  model: "salesOrderItem",    convert: toSalesOrderItem },
  { file: "05_sales_partners.csv",     model: "salesPartner",      convert: toSalesPartner },
  { file: "07_pricing_conditions.csv", model: "pricingCondition",  convert: toPricingCondition },
  { file: "08_deliveries.csv",         model: "delivery",          convert: toDelivery },
  { file: "09_delivery_items.csv",     model: "deliveryItem",      convert: toDeliveryItem },
  { file: "10_invoices.csv",           model: "invoice",           convert: toInvoice },
  { file: "11_invoice_items.csv",      model: "invoiceItem",       convert: toInvoiceItem },
  { file: "12_payments.csv",           model: "payment",           convert: toPayment },
  { file: "13_credit_memos.csv",       model: "creditMemo",        convert: toCreditMemo },
];

async function seed() {
  console.log("═══════════════════════════════════════════════════════");
  console.log("  SAP Order-to-Cash — Full Database Seed");
  console.log("═══════════════════════════════════════════════════════\n");

  // Delete in reverse order (child tables first) to respect FK constraints
  console.log("Clearing existing data...");
  for (const step of [...pipeline].reverse()) {
    await prisma[step.model].deleteMany();
  }
  console.log("  Done\n");

  // Insert in forward order (parent tables first)
  console.log("Loading CSV data...\n");
  for (const step of pipeline) {
    const rows = parseCSV(join(csvDir, step.file));
    const data = rows.map(step.convert);
    const count = await batchInsert(step.model, data);
    console.log(`  ✓ ${step.model.padEnd(20)} ${String(count).padStart(6)} records  (${step.file})`);
  }

  // Summary
  console.log("\n═══════════════════════════════════════════════════════");
  console.log("  Verification");
  console.log("═══════════════════════════════════════════════════════\n");
  for (const step of pipeline) {
    const count = await prisma[step.model].count();
    console.log(`  ${step.model.padEnd(20)} ${String(count).padStart(6)} rows`);
  }
  console.log("\n✅ Seed complete!");
}

seed()
  .catch(err => {
    console.error("Seed failed:", err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
# O2C AI Suite

An AI-powered **Order-to-Cash** management system built with **LangGraph multi-agent orchestration**, **AWS Bedrock (Claude Sonnet 4.5)**, and a **React** frontend. The system uses a supervisor pattern to route natural-language queries to 6 specialist agents backed by 44+ database tools, covering the entire O2C lifecycle — from customer onboarding through sales orders, deliveries, invoicing, payments, and credit memos.

![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent-blue)
![LLM](https://img.shields.io/badge/LLM-Claude%20Sonnet%204.5-orange)
![Framework](https://img.shields.io/badge/Framework-LangGraph-green)
![Database](https://img.shields.io/badge/DB-PostgreSQL-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%2019-61DAFB)

---

## Table of Contents

- [Architecture](#architecture)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Multi-Agent System](#multi-agent-system)
  - [Supervisor Agent](#supervisor-agent)
  - [Customer Agent](#customer-agent)
  - [Order Agent](#order-agent)
  - [Fulfillment Agent](#fulfillment-agent)
  - [Finance Agent](#finance-agent)
  - [Analytics Agent](#analytics-agent)
  - [RAG Agent](#rag-agent)
- [Tools Reference](#tools-reference)
- [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
- [Database Schema](#database-schema)
- [RAG Pipeline](#rag-pipeline)
- [MCP Server](#mcp-server)
- [API Endpoints](#api-endpoints)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Seed Data](#seed-data)
- [Example Queries](#example-queries)
- [Frontend](#frontend)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Frontend (React 19 + Vite 6)                  │
│   ChatInterface │ Sidebar (Documents) │ ApprovalCard │ Theme     │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (REST)
┌────────────────────────────▼─────────────────────────────────────┐
│                   FastAPI Backend (Python)                        │
│         /api/chat  │  /api/upload  │  /api/documents             │
└─────────┬──────────────────────────────────────┬─────────────────┘
          │                                      │
          ▼                                      ▼
┌─────────────────────────┐           ┌────────────────────────┐
│   LangGraph StateGraph  │           │    RAG Pipeline        │
│   (Supervisor Pattern)  │           │    ┌────────────────┐  │
│                         │           │    │ Document Proc   │  │
│   ┌───────────────┐     │           │    │ (PDF/DOCX/CSV) │  │
│   │  Supervisor   │     │           │    └───────┬────────┘  │
│   │  (Router)     │     │           │            │           │
│   └───┬───┬───┬───┘     │           │    ┌───────▼────────┐  │
│       │   │   │         │           │    │ Titan Embed v2 │  │
│   ┌───▼┐ ┌▼──┐ ┌▼───┐  │           │    └───────┬────────┘  │
│   │Cust│ │Ord│ │Fin │  │           │            │           │
│   └────┘ └───┘ └────┘  │           │    ┌───────▼────────┐  │
│   ┌────┐ ┌────┐ ┌────┐ │           │    │   Pinecone     │  │
│   │Fulf│ │Anly│ │RAG │ │           │    │  Vector Store  │  │
│   └────┘ └────┘ └────┘ │           │    └────────────────┘  │
│                         │           └────────────────────────┘
│   44+ LangChain Tools   │
└──────────┬──────────────┘
           │
     ┌─────▼──────┐    ┌──────────────────┐
     │  AWS        │    │  PostgreSQL      │
     │  Bedrock    │    │  (AWS RDS)       │
     │  Claude 4.5 │    │  12 tables,      │
     │             │    │  ~36K records     │
     └─────────────┘    └──────────────────┘
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Agent Orchestration** | LangGraph supervisor routes queries to 6 specialist agents — each with domain-specific tools and system prompts |
| **44+ Database Tools** | Full CRUD + analytics across customers, orders, deliveries, invoices, payments, and credit memos |
| **Human-in-the-Loop** | Approval interrupts for credit limit violations, payment reversals, order cancellations with downstream docs, and high-value credit memos |
| **RAG Document Search** | Upload O2C policy docs (PDF/DOCX/TXT/CSV) and query them via semantic search with Pinecone |
| **MCP Server** | All tools exposed via Model Context Protocol for external AI assistants |
| **Session Persistence** | LangGraph MemorySaver checkpointer maintains conversation state across turns |
| **Dark/Light Theme** | Toggle between themes in the frontend |
| **Infinite Loop Protection** | Dual-layer: smart early-exit detection + hard recursion limit (30 hops) |
| **Token Optimization** | All database queries use LIMIT clauses to prevent context overflow |

---

## Tech Stack

### Backend
| Component | Technology |
|-----------|-----------|
| Web Framework | FastAPI 0.115+ |
| Agent Orchestration | LangGraph 0.2.60+ |
| LLM | AWS Bedrock — Claude Sonnet 4.5 (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| Embeddings | Amazon Titan Embed Text v2 (1024-dim) |
| Vector Store | Pinecone |
| Database | PostgreSQL (AWS RDS) via `asyncpg` |
| MCP | Model Context Protocol SDK 1.0+ |

### Frontend
| Component | Technology |
|-----------|-----------|
| UI Framework | React 19 |
| Build Tool | Vite 6 |
| Markdown Rendering | react-markdown 9 |

### Infrastructure
| Component | Technology |
|-----------|-----------|
| Database Schema | Prisma ORM (schema + migrations + seeding) |
| Cloud Provider | AWS (Bedrock, RDS) |
| LLM Provider | AWS Bedrock |

---

## Project Structure

```
o2c-ai-suite/
├── README.md
├── .env                              # Environment variables
├── .gitignore
│
├── o2c-rag/                          # Main application
│   ├── backend/
│   │   ├── config.py                 # AWS, Bedrock, Pinecone, RAG config
│   │   ├── main.py                   # FastAPI app with all endpoints
│   │   ├── requirements.txt          # Python dependencies
│   │   ├── agents/
│   │   │   ├── state.py              # AgentState TypedDict
│   │   │   ├── graph.py              # LangGraph StateGraph builder
│   │   │   ├── supervisor.py         # Supervisor router agent
│   │   │   ├── customer_agent.py     # Customer specialist
│   │   │   ├── order_agent.py        # Sales order specialist
│   │   │   ├── fulfillment_agent.py  # Delivery specialist
│   │   │   ├── finance_agent.py      # Invoice/payment/credit memo specialist
│   │   │   ├── analytics_agent.py    # Cross-domain reporting specialist
│   │   │   └── rag_agent.py          # Document search specialist
│   │   ├── tools/
│   │   │   ├── customer_tools.py     # 6 tools: get, list, create, update, deactivate, 360-view
│   │   │   ├── material_tools.py     # 5 tools: get, list, create, update, deactivate
│   │   │   ├── order_tools.py        # 7 tools: get, list, create, update, add_item, cancel, history
│   │   │   ├── delivery_tools.py     # 5 tools: get, list, create, update_status, update_tracking
│   │   │   ├── invoice_tools.py      # 5 tools: get, list, create, overdue, aging
│   │   │   ├── payment_tools.py      # 4 tools: get, list, record, reverse
│   │   │   ├── credit_memo_tools.py  # 4 tools: get, list, create, approve
│   │   │   ├── analytics_tools.py    # 6 tools: orders, revenue, payments, delivery, aging, pipeline
│   │   │   └── rag_tools.py          # 2 tools: search_documents, get_uploaded_documents
│   │   ├── rag/
│   │   │   ├── chain.py              # History-aware RAG chain
│   │   │   ├── document_processor.py # PDF/DOCX/CSV loader & chunking
│   │   │   └── vector_store.py       # Pinecone integration
│   │   ├── db/
│   │   │   └── connection.py         # asyncpg connection pool
│   │   └── mcp_server/
│   │       └── server.py             # MCP server exposing all tools
│   │
│   └── frontend/
│       ├── index.html
│       ├── package.json
│       ├── vite.config.js            # Dev proxy → localhost:8000
│       └── src/
│           ├── main.jsx              # React entry point
│           ├── App.jsx               # Layout: Sidebar + Chat + Theme
│           ├── api.js                # API client (chat, upload, resume)
│           └── components/
│               ├── ChatInterface.jsx # Chat UI with agent badges
│               ├── Sidebar.jsx       # Document management panel
│               ├── ApprovalCard.jsx  # HITL approval/reject UI
│               ├── ThemeToggle.jsx   # Dark/light mode toggle
│               └── FileUpload.jsx    # Document upload
│
└── o2c-setup/                        # Database setup & seeding
    ├── package.json
    ├── prisma.config.ts
    ├── prisma/
    │   ├── schema.prisma             # 12 models, 9 enums
    │   ├── seed.js                   # CSV-based data seeding
    │   ├── csv/                      # 12 CSV files (~36K rows)
    │   └── migrations/               # Database migrations
    └── src/db/
        └── client.js                 # Prisma client
```

---

## Multi-Agent System

The system uses a **supervisor pattern** built with LangGraph's `StateGraph`. The supervisor agent receives every user query and routes it to the appropriate specialist, which executes tools and returns a response. The supervisor then terminates the conversation or routes to another agent if needed.

```
User Query → Supervisor → Specialist Agent → Tool Execution → Supervisor → Response
```

### Supervisor Agent

**Role:** Intelligent router — no tools of its own, only routing decisions.

Uses Claude with structured output (`RouteDecision`) to classify queries and route to one of 6 specialists. Includes smart early-exit detection: if a specialist already produced an answer, the supervisor routes directly to `__end__` without making another LLM call.

**Routing Rules:**

| Query Type | Routed To |
|------------|-----------|
| Customer data (list, count, filter, search, 360-view) | `customer_agent` |
| Sales order operations (create, cancel, status, history) | `order_agent` |
| Delivery and shipping management | `fulfillment_agent` |
| Invoices, payments, credit memos, billing | `finance_agent` |
| Cross-domain reports (revenue, KPIs, aging, pipeline) | `analytics_agent` |
| Document/policy/SOP questions | `rag_agent` |

### Customer Agent

**Tools (6):** `get_customer`, `list_customers`, `create_customer`, `update_customer`, `deactivate_customer`, `get_customer_360`

Handles customer master data: lookups by ID/number, filtered searches (by country, group, credit limit), onboarding new customers, updates, soft-deletes, and 360-degree views showing all orders, invoices, payments, and credit utilization.

### Order Agent

**Tools (7):** `get_sales_order`, `list_sales_orders`, `create_sales_order`, `update_sales_order_status`, `add_sales_order_item`, `cancel_sales_order`, `get_sales_order_history`

Manages the full sales order lifecycle: creation with line items (auto-calculates 18% tax), status transitions (DRAFT → OPEN → IN_DELIVERY → COMPLETED), cancellation with HITL approval when downstream documents exist, and document flow tracing.

### Fulfillment Agent

**Tools (5):** `get_delivery`, `list_deliveries`, `create_delivery`, `update_delivery_status`, `update_delivery_tracking`

Handles delivery creation from sales orders, status progression (PLANNED → PICKED → PACKED → SHIPPED → DELIVERED), carrier/tracking updates, and shipment monitoring.

### Finance Agent

**Tools (15):** All invoice tools (5) + payment tools (4) + credit memo tools (4) + overdue/aging (2)

Manages invoicing from deliveries, payment recording and reversals (HITL required), credit memo creation and approval (HITL for amounts > $5,000), overdue invoice tracking, and aging analysis.

### Analytics Agent

**Tools (6):** `get_order_analytics`, `get_revenue_analytics`, `get_payment_analytics`, `get_delivery_performance`, `get_customer_aging_report`, `get_o2c_pipeline_summary`

Provides cross-domain business intelligence: order metrics with trends, revenue breakdowns (by customer/material/month), collection rates, delivery KPIs, AR aging, and end-to-end pipeline snapshots.

### RAG Agent

**Tools (2):** `search_documents`, `get_uploaded_documents`

Performs semantic search over uploaded O2C policy documents, SOPs, and contracts using Pinecone vector embeddings. Cites source documents and page/chunk numbers in responses.

---

## Tools Reference

| Domain | Tool | Description |
|--------|------|-------------|
| **Customer** | `get_customer` | Fetch customer by ID or customer number |
| | `list_customers` | Search/filter by name, group, country, credit limit |
| | `create_customer` | Onboard with full business details |
| | `update_customer` | Update any customer fields |
| | `deactivate_customer` | Soft-delete a customer |
| | `get_customer_360` | 360° view: orders, invoices, payments, credit utilization |
| **Material** | `get_material` | Fetch material by ID or number (MAT-XXXX) |
| | `list_materials` | Search by description, group, price range |
| | `create_material` | Create material master record |
| | `update_material` | Update material fields |
| | `deactivate_material` | Soft-delete a material |
| **Order** | `get_sales_order` | Fetch order with items, partners, pricing |
| | `list_sales_orders` | Search by customer, status, date, amount |
| | `create_sales_order` | Create order with line items (auto-calc tax) |
| | `update_sales_order_status` | Advance order status |
| | `add_sales_order_item` | Add line item to DRAFT/OPEN order |
| | `cancel_sales_order` | Cancel order (HITL if downstream docs exist) |
| | `get_sales_order_history` | Full document flow trace |
| **Delivery** | `get_delivery` | Fetch delivery with items and tracking |
| | `list_deliveries` | Search by order, status, carrier, date |
| | `create_delivery` | Create delivery from sales order |
| | `update_delivery_status` | Progress: PLANNED → DELIVERED |
| | `update_delivery_tracking` | Update tracking number and carrier |
| **Invoice** | `get_invoice` | Fetch invoice with items and payments |
| | `list_invoices` | Search by customer, status, date, overdue |
| | `create_invoice` | Create invoice from delivered delivery |
| | `get_overdue_invoices` | All past-due unpaid invoices |
| | `get_invoice_aging_report` | Aging buckets: current, 30, 60, 90+ days |
| **Payment** | `get_payment` | Fetch payment by number (PAY-XXXX) |
| | `list_payments` | Search by customer, invoice, method, status |
| | `record_payment` | Record payment (auto-updates invoice status) |
| | `reverse_payment` | Reverse payment (**HITL required**) |
| **Credit Memo** | `get_credit_memo` | Fetch credit memo (CM-XXXX) |
| | `list_credit_memos` | Search by customer, status, reason |
| | `create_credit_memo` | Create against invoice |
| | `approve_credit_memo` | Approve/post (**HITL if > $5,000**) |
| **Analytics** | `get_order_analytics` | Order counts, amounts, status, trends |
| | `get_revenue_analytics` | Revenue by customer/material/month |
| | `get_payment_analytics` | Collection rate, avg days to pay |
| | `get_delivery_performance` | Delivery KPIs by carrier/status |
| | `get_customer_aging_report` | Outstanding AR by customer |
| | `get_o2c_pipeline_summary` | End-to-end pipeline snapshot |
| **RAG** | `search_documents` | Semantic search uploaded documents |
| | `get_uploaded_documents` | List all uploaded docs |

---

## Human-in-the-Loop (HITL)

The system pauses execution and requests human approval for sensitive operations. LangGraph's `interrupt()` mechanism saves the full graph state, and `Command(resume=...)` resumes execution after approval/rejection.

| Scenario | Trigger Condition | What Happens |
|----------|-------------------|--------------|
| **Credit Limit Exceeded** | New order would push customer over credit limit | Shows order details, current utilization, and asks for override approval |
| **Order Cancellation** | Cancel order that has active deliveries or invoices | Shows linked documents and asks for confirmation |
| **Payment Reversal** | Any payment reversal request | Shows payment details, linked invoice, and impact on invoice status |
| **High-Value Credit Memo** | Credit memo amount exceeds $5,000 | Shows credit memo details and asks for approval |
| **Bulk Operations** | Mass status changes across multiple records | Shows affected records and asks for confirmation |

The frontend renders an `ApprovalCard` component with the context, details, and Approve/Reject buttons. The user's decision (with optional comment) is sent to `/api/chat/resume`.

---

## Database Schema

12 PostgreSQL tables modeled with Prisma, covering the full O2C data model:

### Entity Relationship

```
Customer ─┬── SalesOrder ──┬── SalesOrderItem ──── PricingCondition
           │                ├── SalesPartner
           │                ├── Delivery ──── DeliveryItem
           │                ├── Invoice ──── InvoiceItem
           │                └── CreditMemo
           ├── Invoice
           ├── Payment
           └── CreditMemo
                                Invoice ──── Payment
```

### Models

| Model | Key Fields | Records |
|-------|-----------|---------|
| **Customer** | customerNumber (CUST-XXXX), name, country, creditLimit, paymentTerms, customerGroup | 50 |
| **Material** | materialNumber (MAT-XXXX), description, materialGroup, basePrice | 100 |
| **SalesOrder** | orderNumber (SO-XXXX), status, totalGrossAmount, orderDate | 2,000 |
| **SalesOrderItem** | itemNumber, materialId, quantity, unitPrice, netAmount | 5,017 |
| **SalesPartner** | partnerFunction (SOLD_TO, SHIP_TO, BILL_TO, PAYER) | 4,001 |
| **PricingCondition** | conditionType, conditionValue, isPercentage | 15,051 |
| **Delivery** | deliveryNumber (DL-XXXX), status, carrier, trackingNumber | 1,381 |
| **DeliveryItem** | deliveredQuantity, batchNumber | 3,448 |
| **Invoice** | invoiceNumber (INV-XXXX), status, dueDate, totalGrossAmount | 1,151 |
| **InvoiceItem** | quantity, unitPrice, netAmount | 2,882 |
| **Payment** | paymentNumber (PAY-XXXX), amount, paymentMethod, status | 860 |
| **CreditMemo** | creditMemoNumber (CM-XXXX), reason, totalAmount, status | 56 |

### Enumerations

| Enum | Values |
|------|--------|
| CustomerGroup | DOMESTIC, EXPORT, INTERCOMPANY |
| SalesOrderStatus | DRAFT, OPEN, IN_DELIVERY, COMPLETED, CANCELLED |
| DeliveryStatus | PLANNED, PICKED, PACKED, SHIPPED, DELIVERED |
| InvoiceStatus | OPEN, PARTIALLY_PAID, PAID, CANCELLED |
| PaymentMethod | BANK_TRANSFER, CREDIT_CARD, CHECK, CASH |
| PaymentStatus | PENDING, CLEARED, REVERSED |
| CreditMemoStatus | DRAFT, APPROVED, POSTED, CANCELLED |

---

## RAG Pipeline

Upload O2C documents (policies, SOPs, contracts) and query them using natural language.

| Stage | Component | Detail |
|-------|-----------|--------|
| **Load** | `document_processor.py` | Supports PDF, DOCX, TXT, CSV |
| **Chunk** | `RecursiveCharacterTextSplitter` | 1000 chars, 200 overlap |
| **Embed** | Amazon Titan Embed Text v2 | 1024 dimensions |
| **Store** | Pinecone | Free tier: 2 GB, ~400K vectors |
| **Retrieve** | Similarity search | Top-5 chunks per query |
| **Generate** | Claude Sonnet 4.5 | History-aware QA chain with source citations |

---

## MCP Server

All 44+ tools are exposed via **Model Context Protocol** (`backend/mcp_server/server.py`), allowing external AI assistants (Claude Desktop, other MCP clients) to interact with the O2C system.

- `list_tools()` — Returns all available tools with JSON Schema definitions
- `call_tool(name, arguments)` — Invokes any tool by name
- Runs over stdio for subprocess invocation

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/chat` | Send message → LangGraph agent response |
| `POST` | `/api/chat/resume` | Resume paused HITL thread with approval/rejection |
| `POST` | `/api/upload` | Upload document for RAG (PDF/DOCX/TXT/CSV) |
| `GET` | `/api/documents` | List uploaded documents |
| `DELETE` | `/api/documents/{id}` | Delete document and vectors |
| `DELETE` | `/api/sessions/{id}` | Clear session history |
| `GET` | `/api/stats` | Document count, Pinecone index stats |

### Chat Request/Response

```json
// POST /api/chat
{
  "message": "How many customers do we have from Europe?",
  "session_id": "optional-uuid"
}

// Response
{
  "answer": "You have 11 customers from the European region...",
  "session_id": "uuid",
  "sources": [],
  "agent": "customer_agent",
  "approval_request": null
}
```

### HITL Approval

```json
// POST /api/chat/resume
{
  "thread_id": "uuid",
  "approved": true,
  "comment": "Approved by manager"
}
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL database (AWS RDS or local)
- AWS account with Bedrock access (Claude Sonnet 4.5 enabled)
- Pinecone account (free tier works)

### 1. Clone the Repository

```bash
git clone https://github.com/SaiSrivatsav/o2c-ai-suite.git
cd o2c-ai-suite
```

### 2. Setup Environment Variables

Create a `.env` file in the project root:

```env
# AWS Credentials
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require

# Pinecone
PINECONE_API_KEY=your-pinecone-api-key

# Optional overrides
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
RETRIEVER_TOP_K=5
```

### 3. Setup Database

```bash
cd o2c-setup
npm install
npx prisma migrate deploy
npx prisma db seed
```

### 4. Start Backend

```bash
cd o2c-rag/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. Start Frontend

```bash
cd o2c-rag/frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | Yes | — | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | AWS IAM secret key |
| `AWS_REGION` | No | `us-east-1` | AWS region for Bedrock |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `PINECONE_API_KEY` | Yes | — | Pinecone API key |
| `BEDROCK_MODEL_ID` | No | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Bedrock model ID |
| `CHUNK_SIZE` | No | `1000` | RAG document chunk size |
| `CHUNK_OVERLAP` | No | `200` | RAG chunk overlap |
| `RETRIEVER_TOP_K` | No | `5` | Number of retrieved chunks |

---

## Seed Data

The `o2c-setup/prisma/csv/` directory contains 12 CSV files with realistic O2C data totaling ~36,000 records:

| File | Table | Records |
|------|-------|---------|
| `01_customers.csv` | Customer | 50 |
| `02_materials.csv` | Material | 100 |
| `03_sales_orders.csv` | SalesOrder | 2,000 |
| `04_sales_order_items.csv` | SalesOrderItem | 5,017 |
| `05_sales_partners.csv` | SalesPartner | 4,001 |
| `07_pricing_conditions.csv` | PricingCondition | 15,051 |
| `08_deliveries.csv` | Delivery | 1,381 |
| `09_delivery_items.csv` | DeliveryItem | 3,448 |
| `10_invoices.csv` | Invoice | 1,151 |
| `11_invoice_items.csv` | InvoiceItem | 2,882 |
| `12_payments.csv` | Payment | 860 |
| `13_credit_memos.csv` | CreditMemo | 56 |

The seed script (`prisma/seed.js`) inserts data in batches of 500, respecting foreign key constraints, and verifies final counts.

---

## Example Queries

**Customer Queries:**
- "How many customers do we have from Europe?"
- "Show me all EXPORT customers"
- "Give me a 360-degree view of CUST-0001"
- "Onboard a new customer named Acme Corp"

**Order Management:**
- "Show me the first 10 sales orders"
- "What's the status of order SO-0135?"
- "Cancel order SO-0135"
- "Create a new order for CUST-0010 with 5 units of MAT-0001"

**Delivery & Fulfillment:**
- "List all deliveries for SO-0050"
- "Update delivery DL-0001 to SHIPPED"

**Finance:**
- "Show overdue invoices"
- "Record a $5,000 payment for INV-0001 via bank transfer"
- "Reverse payment PAY-0001"
- "Create a credit memo for INV-0050 — pricing error, $2,000"

**Analytics:**
- "Show me the O2C pipeline summary"
- "Revenue analytics for Q1 2025 grouped by customer"
- "What's our payment collection rate?"
- "Customer aging report"

**RAG (after uploading documents):**
- "What is our return policy?"
- "What are the SOP steps for credit memo approval?"

---

## Frontend

The React frontend provides:

- **Chat Interface** — Natural language conversation with agent badges showing which specialist handled the query
- **Document Sidebar** — Upload, view, and delete O2C policy documents for RAG
- **Approval Cards** — Interactive approve/reject cards for HITL scenarios with context details and optional comments
- **Theme Toggle** — Switch between dark and light mode
- **New Chat** — Reset conversation to start a fresh session

---

## License

This project is for educational and demonstration purposes.

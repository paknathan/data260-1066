# AI_USE.md

### 1. What You Used an AI Assistant For and What You Did Yourself

* **AI Assistant Assistance:**
  * **Code Generation:** Drafting boilerplate FastAPI endpoints (`/incidents-naive`, `/incidents-fixed`), creating synthetic data seeding scripts (`seed.py`), and writing the benchmark latency timing script (`benchmark.py`).
  * **RAG Pipeline Architecture:** Setting up vector indexing with FAISS, document chunking logic, and prompt template structures for No-RAG, Basic-RAG, and Context-Engineered RAG in `rag.py`.
  * **Documentation & Analysis:** Structuring performance comparison tables, formatting mathematical latency calculations, and drafting essay-formatted analysis sections for the final homework report.

* **Independent Work:**
  * **Environment & Infrastructure Setup:** Configuring local MySQL `_rel` database schemas, managing environment variables (`DATABASE_URL`), and resolving local system dependency conflicts (macOS Xcode licenses, Homebrew, and Python virtual environments).
  * **Execution & Data Collection:** Running server processes locally, executing benchmarking sweeps across page sizes 10, 50, and 200, and logging raw timings directly to `reports/hw04/raw/`.
  * **API & Database Verification:** Authenticating session tokens, capturing Postman request/response screenshots across all 6 test scenarios, and running manual SQL `EXPLAIN` queries in the terminal to inspect query execution plans.

---

### 2. AI-Produced Output That Was Wrong or Unsuitable

* **Code Structure & Execution Sequencing:** 
  * In `main.py`, the AI generated route decorators (`@app.get("/incidents-naive")`) placed above the `app = FastAPI(...)` instantiation line, which would trigger a `NameError` on server startup.
  * When running `benchmark.py`, the AI assumed the script could run standalone without explicitly prompting to start the Uvicorn server process first, leading to a `ConnectionRefusedError: [Errno 61] Connection refused`.
* **Dependency Assumptions:** 
  * The AI generated an `import sentence_transformers` script without accounting for default TensorFlow initialization inside Anaconda environments. On macOS CPUs lacking x86 AVX instruction sets, this caused TensorFlow to throw an AVX execution crash during embedding generation.

---

### 3. How You Detected the Problem or Verified the Result

* **Stack Trace Analysis:** 
  * Inspected the Python tracebacks to locate the `ConnectionRefusedError` on port `8166` and identified that `main.py` was not running in an active terminal process.
  * Checked the C++ logging output from TensorFlow during `rag.py` execution: *"The TensorFlow library was compiled to use AVX instructions, but these aren't available on your machine."*
* **Database Query Verification:** 
  * Verified query counts independently by enabling SQLAlchemy statement logging (`echo=True`) and running `EXPLAIN SELECT * FROM incident_logs WHERE incident_id = 15;` directly in MySQL before and after index creation. Confirmed that adding the index transitioned the execution plan from a full table scan (`type: ALL`, 200 rows) to an indexed lookup (`type: ref`, 1 row).

---

### 4. What You Changed and Why It Works Now

* **Reordered Server Definitions & Process Lifecycle:** 
  * Moved `app = FastAPI(...)` to the top of `main.py` directly after imports so all `@app.get` decorators reference a valid FastAPI instance.
  * Established a two-terminal workflow: Terminal 1 runs `python main.py` to maintain an active HTTP listener, while Terminal 2 executes `python benchmark.py`.
* **Suppressed Unused Framework Overhead:** 
  * Set `USE_TF=0` in the environment to force Hugging Face `transformers` and `sentence-transformers` to bypass TensorFlow and rely purely on PyTorch, resolving the AVX CPU instruction mismatch.
* **Optimized Data Access Pattern:** 
  * Replaced lazy loop evaluation in `/incidents-naive` with `joinedload(IncidentModel.logs)` in `/incidents-fixed`. This consolidated $N+1$ individual database round-trips into a single SQL `LEFT OUTER JOIN`, reducing p50 latency on page size 200 from **40.32 ms** to **5.16 ms** (an 87.2% speed improvement).
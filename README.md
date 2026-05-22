# agents-

# AI Agent Development Lab

This repository is a dedicated space for the **design, development, and experimentation of autonomous AI agents**. Our goal is to create agents that perceive, reason, plan, and act within simulated or real environments using modular, scalable, and adaptable architectures.

We leverage AI-assisted tools such as GitHub Copilot and large language models to enhance developer productivity, accelerate experimentation, and explore novel approaches—but the focus remains firmly on **building better agents**, not just on how they’re built.

---

## 🎯 Mission

To create a flexible, collaborative ecosystem for AI agent development that supports:

- Exploration of diverse agent architectures, behaviors, and capabilities
- Reusable and composable components (planners, memory, sensors, etc.)
- Fast iteration using AI-assisted tooling
- Transparent documentation of agent logic, decisions, and design evolution

This is a hands-on lab—not a polished product. Expect rapid prototyping, imperfect code, weird experiments, and a growing library of intelligent systems.

---

## 🧱 What You Can Build

- Autonomous agents with custom planning strategies (LLM, rule-based, RL, hybrid)
- Memory systems (episodic, vector, contextual, stateless)
- Modular behavior layers and execution loops
- Simulated environments for benchmarking adaptation, planning, and learning
- Evaluation pipelines to track agent performance and behavioral drift
- Prompt-driven components that complement classical logic

---

## 📦 Repo Structure

```
/
├── agents/ # Full agents with defined loops and modular construction
├── modules/ # Pluggable logic: planners, memory, perception, etc.
├── sandbox/ # Environments and tasks for testing agents
├── prompts/ # Reference prompts for LLM-based planning or memory
├── logs/
│ ├── decisions/ # Design decisions and architecture changes
│ └── experiments.md # Experiment tracking log
├── utils/ # Shared utilities and support code
├── README.md # Project overview
└── CONTRIBUTING.md # How to contribute
```

---


## 🧠 Development Philosophy

- **Agents First**  
  Our focus is on building high-quality, intelligent agents. The tools, techniques, and strategies serve that purpose.

- **Modularity Always**  
  Agents should be built from interchangeable components—allowing for easy comparison, substitution, and experimentation.

- **AI-Assisted, Not AI-Owned**  
  Use tools like Copilot, ChatGPT, or Claude to help brainstorm, scaffold, and prototype—but always validate, refine, and take ownership of logic.

- **Think, Build, Test, Repeat**  
  Begin with a hypothesis or behavior goal, build toward it, test it thoroughly, and document the result—success or failure.

- **Log the Journey**  
  Track every meaningful insight, mistake, or behavior change in `/logs/`. Decision rationale is as important as code.

---

## 🚀 Getting Started

1. Clone or fork this repo.
2. Explore existing agents in `/agents/`.
3. Choose a component to modify or build new functionality under `/modules/`.
4. Run agents using the testing environments in `/sandbox/`.
5. Use AI tools to assist as needed, but ensure human-reviewed output.
6. Document what you learned in `/logs/experiments.md`.
7. Submit a pull request summarizing:
   - What you built or changed
   - What worked or failed
   - What was AI-assisted
   - Next steps or open questions

---

## 🛠 Tools We Use

- Python
- GitHub Copilot (optional)
- GPT-based tools (ChatGPT, Claude, etc.)
- Markdown for logs, design notes, and prompts
- Optional frameworks: LangChain, AutoGen, CrewAI (experimentally supported)

---

## 🤝 Contributing

We welcome contributors of all skill levels and backgrounds. Whether you're optimizing a planner, testing a new memory schema, or just documenting a test—your input matters.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

---

## 📄 VisualCron Docs → PDF Generation

A local offline script (`scripts/build_doc_pdfs.py`) converts a folder of
Markdown documentation files into grouped PDFs — one PDF per folder in the
docs tree.

### Prerequisites

You need **one** of the following PDF tools installed locally:

| Tool | Install |
|------|---------|
| **pandoc** *(recommended)* | https://pandoc.org/installing.html |
| wkhtmltopdf *(pandoc engine)* | https://wkhtmltopdf.org/downloads.html |
| xelatex / pdflatex *(pandoc engine)* | Install a TeX distribution (e.g. MiKTeX, TeX Live) |
| Google Chrome or Chromium *(fallback)* | Already installed on most systems |
| Microsoft Edge *(fallback)* | Already installed on Windows |

No internet access is required at runtime — the script uses only your
locally installed tools and standard Python libraries (Python 3.7+).

### Quick start

```bash
# 1. Clone or download the docs repo you want to convert, e.g.:
#    git clone https://github.com/smatechnologies/visualcron-docs.git

# 2. From the root of *this* repo, run:
python scripts/build_doc_pdfs.py --source-path /path/to/visualcron-docs/docs

# 3. PDFs are written to output-pdf/  (one per folder group)
#    A summary report is written to output-pdf/build-report.json
```

### Options

```
--source-path PATH   (required) Root directory containing .md files
--output-path PATH   Where to write PDFs (default: output-pdf/)
--config FILE        JSON config file (default: scripts/config.json if present)
--dry-run            Scan and list groups without generating any PDFs
```

### Dry run (no PDF tool required)

```bash
python scripts/build_doc_pdfs.py --source-path /path/to/docs --dry-run
```

This prints the discovered folder groups and file counts without invoking
any external converter — useful for previewing how the docs will be grouped.

### Grouping logic

- Each folder that contains `.md` files directly becomes **one PDF**.
- Nested sub-folders each become their own separate PDF.
- `index.md` / `readme.md` are sorted to the top of each PDF; all other
  files are sorted alphabetically (numeric prefixes sorted numerically).
- Relative image references are automatically rewritten to absolute paths so
  images are embedded correctly regardless of where the temp file is created.

### Output naming

| Source folder | Output PDF |
|---------------|------------|
| `docs/commands/` | `output-pdf/commands.pdf` |
| `docs/client-user-interface/` | `output-pdf/client-user-interface.pdf` |
| `docs/client-user-interface/toolbar/` | `output-pdf/client-user-interface--toolbar.pdf` |
| `docs/` *(root-level .md files)* | `output-pdf/documentation.pdf` |

### Running the tests

```bash
python -m unittest discover -v
```

All 38 unit tests run without any external dependencies.

---

## 📌 Final Notes

This repository is about pushing agent intelligence forward.  
It's about learning how to make systems that adapt, observe, plan, and act. 
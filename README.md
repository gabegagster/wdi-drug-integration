# Web Data Integration: Pharmaceutical Drug Data

This repository contains the codebase and documentation for our Web Data Integration (WDI) student project. We are building an integrated dataset of pharmaceutical drugs, focusing on **active substances** (e.g., atorvastatin, paracetamol) by combining data from US regulators, EU regulators, and public knowledge graphs.

## Datasets
1. **Drugs@FDA:** US approved drugs (CSV)
2. **EMA Medicines:** EU approved drugs (Excel)
3. **Health Canada DPD:** Canadian Drug Product Database (CSV extract, 12 related tables)

## Project Phases
* **Phase I: Data Selection and Translation:** Profiling raw data, handling missing values, and mapping all three sources to a single integrated JSON/XML schema.
* **Phase II: Identity Resolution:** Identifying overlapping active substances across the datasets using similarity measures and blocking techniques via the PyDI framework.
* **Phase III: Data Fusion:** Merging records and resolving data conflicts (e.g., paracetamol vs. acetaminophen) to create a single, clean golden record for each entity.

## Local Setup
Ensure you have Python installed, then install the necessary dependencies for data profiling and extraction:
`bash
pip install -r requirements.txt
`

## Team & Work Split (Phase I)
* **Gabriel:** Requirements compliance, math checks, and final PDF assembly.
* **Özlem:** Use case narrative and entity overlap justification.
* **Anatole & Hai:** Data extraction and profiling (FDA, EMA, Wikidata).
* **Trang:** Target schema design and attribute intersection mapping.

## Repository Structure
```text
wdi-drug-integration/
├── data/
│   ├── 1_raw/                 # Original CSV/Excel from FDA, EMA, and Wikidata
│   ├── 2_translated/          # JSON/XML files mapped to the integrated schema
│   └── 3_fused/               # Final output after PyDI identity resolution & fusion
├── src/
│   ├── data_collection/       # Python scripts for Wikidata SPARQL queries
│   ├── mapforce/              # MapForce mapping files (.mfd)
│   ├── identity_resolution/   # PyDI scripts for blocking and similarity measures
│   └── data_fusion/           # PyDI scripts for conflict resolution
├── docs/
│   ├── outline/              # The 4-page project abstract (PDF)
│   └── final_report/          # Springer CS LaTeX files and final 12-page report
├── .gitignore                 # Excludes large raw datasets
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview

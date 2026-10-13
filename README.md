# Data pipeline for scraping Mubawab real-estate listings

A production-ready Python data pipeline for collecting, transforming, and storing real-estate listings from Mubawab. The project is designed to extract listing data at scale, normalize it into a consistent schema, and make it available for dashboards, analytics, or downstream ETL jobs.

## Overview

This project pulls property ads from Mubawab, captures key listing details such as price, location, area, bedroom count, and URL, then stores them in a structured format. The pipeline can be run manually or scheduled periodically to keep the dataset fresh.

Typical use cases include:
- Monitoring market prices in a city or region
- Building analytics dashboards for real-estate trends
- Enriching downstream ML and forecasting pipelines
- Tracking listing availability over time

## Features

- Scrapes property listings from Mubawab pages
- Extracts structured fields from each ad
- Handles pagination and multiple property search results
- Normalizes inconsistent fields before loading
- Stores raw and cleaned data separately
- Supports local development and containerized execution
- Can be scheduled via cron, Airflow, or a CI/CD workflow

## Architecture

The pipeline usually follows a simple ETL flow:

1. Extraction
   - Fetch listing pages from Mubawab
   - Collect metadata and listing details
   - Save raw HTML/JSON if needed

2. Transformation
   - Clean and standardize values
   - Normalize locations, prices, and area units
   - Enrich records with source and scrape timestamps

3. Loading
   - Insert into a relational database or warehouse
   - Publish cleaned data for analysis
   - Store raw data for debugging and reprocessing

4. Orchestration
   - Run at fixed intervals
   - Retry failed runs
   - Track ingestion status and errors

## Tech stack

A typical implementation for this project may use:
- Python 3.11+
- requests or httpx for HTTP calls
- BeautifulSoup, Playwright, or Scrapy for scraping
- pandas for transformations
- PostgreSQL or SQLite for storage
- Docker for local environment consistency
- cron or Apache Airflow for scheduling

## Prerequisites

Before running the project, make sure you have:
- Python 3.11 or newer
- pip or poetry
- Access to the internet
- A database (PostgreSQL recommended)
- Optional: Docker and Docker Compose

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/your-org/mubawab-scraper.git
cd mubawab-scraper
python -m venv .venv
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If your project uses Poetry instead of pip:

```bash
poetry install
```

## Configuration

Create a `.env` file in the project root and define the required values. Example:

```env
MUBAWAB_BASE_URL=https://www.mubawab.com
MUBAWAB_COUNTRY=ma
MUBAWAB_CITY=rabat
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mubawab
DB_USER=postgres
DB_PASSWORD=postgres
SCRAPE_TIMEOUT=30
REQUEST_DELAY=2
LOG_LEVEL=INFO
```

If the project contains a `config.py` or YAML configuration file, use that instead, but keep secrets out of version control.

## Running the scraper

Install this project and its dependencies:

```bash
python -m pip install -e .
```

First, register Mubawab city links from the footer:

```bash
python -m mubawab_scraper scrape --orchestrator ville --city casablanca
```

Scrape one city, or every registered city. The `/ct/` route includes all
property types, so use `--property-type all`. `--action` accepts one action or
`all`; `--max-pages 0` scrapes every page:

```bash
python -m mubawab_scraper scrape --city kenitra --action a-vendre --max-pages 2
python -m mubawab_scraper scrape --city all --action all --max-pages 0
```

The pipeline enriches listings, upserts them into SQLite, stores pagination
metadata per city and action, and exports listing rows to
`data/processed/mubawab_export.csv`. City links are exported separately to
`data/processed/mubawab_villes.csv`.

Export the stored listings again without scraping:

```bash
python -m mubawab_scraper export --fmt csv
```

## Data model

The cleaned dataset should contain a standard set of fields similar to the following:

- id: unique listing identifier
- title: listing title
- price: listing price
- currency: currency code
- property_type: apartment, villa, house, etc.
- city: city or region
- neighborhood: listing district or area
- bedrooms: number of bedrooms
- bathrooms: number of bathrooms
- area: property size
- area_unit: m2 or ft2
- listing_url: Mubawab listing URL
- source: source platform name
- scraped_at: timestamp when data was collected
- created_at: timestamp when inserted into database

## Output

The pipeline may save data in one or more of the following formats:
- Raw HTML snapshots
- JSON lines or JSON files
- CSV export files
- Parquet files for analytics
- PostgreSQL table rows

Recommended storage pattern:
- `raw/`: unprocessed crawler output
- `staging/`: normalized intermediate records
- `processed/`: cleaned final records
- `db/`: database models or migration scripts

## Scheduling

You can schedule the scraper with cron:

```bash
0 * * * * cd /path/to/mubawab-scraper && python src/main.py >> logs/scraper.log 2>&1
```

For larger pipelines, use Airflow, Dagster, or Prefect to manage retries, scheduling, and observability.

## Reliability and anti-bot considerations

When scraping public websites, be careful to avoid unnecessary load and respect site policies:
- Add polite request delays
- Use a realistic User-Agent header
- Handle pagination and rate limiting gracefully
- Capture errors and retry transient failures
- Detect blocked responses or captcha pages
- Log enough detail to debug failures

If Mubawab blocks automated requests, consider using a browser automation layer or a vendor-provided API where available, and always stay within legal and ethical boundaries.

## Testing

Use automated tests for parsing, normalization, and database writes. Example:

```bash
pytest
```

A good minimum suite should include:
- Unit tests for extractor functions
- Tests for price and area normalization
- Validation tests for required fields
- Integration tests for database inserts

## Project structure

A typical project layout is:

```text
mubawab-scraper/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── crawler/
│   ├── extractors/
│   ├── transformers/
│   ├── loaders/
│   └── utils/
├── tests/
├── data/
│   ├── raw/
│   ├── staging/
│   └── processed/
├── logs/
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── README.md
└── LICENSE
```

## Docker usage

If a `Dockerfile` is included, you can run the scraper in a container:

```bash
docker build -t mubawab-scraper .
docker run --rm --env-file .env mubawab-scraper
```

Or with Docker Compose:

```bash
docker-compose up --build
```

## Monitoring and logs

Keep logs for:
- scraper start and end time
- number of pages scraped
- number of listings saved
- errors and retries
- database insert failures

Example log levels:
- `INFO` for routine execution
- `WARNING` for recoverable anomalies
- `ERROR` for failed jobs or blocked requests

## Troubleshooting

Common issues include:
- Empty or malformed HTML pages
- Changed selectors or page structure
- Rate limiting or temporary blocking
- Invalid dates or missing fields
- Database connection failures

When debugging:
- Save a sample HTML page to `data/raw/`
- Log the response status and headers
- Inspect parsing output before insert
- Validate the schema before loading

## Contributing

Contributions are welcome. Before submitting a change:
- Create a feature branch
- Add or update tests for changed behavior
- Ensure code style checks pass
- Update documentation when behavior changes

## License

This project is distributed under the MIT License unless your organization uses a different license policy. See the `LICENSE` file for details if it exists in your repository.

## Summary

This repository is intended to provide a complete and maintainable workflow for collecting Mubawab property listings, transforming them into analytics-ready data, and storing them in a structured database or data warehouse. With the right scheduling and validation layer, it can support long-term market monitoring and reporting.

Overview
========

Welcome to Astronomer! This project was generated after you ran 'astro dev init' using the Astronomer CLI. This readme describes the contents of the project, as well as how to run Apache Airflow on your local machine.

Project Contents
================

Your Astro project contains the following files and folders:

- dags: This folder contains the Python files for your Airflow Dags. By default, this directory includes one example Dag:
    - `example_astronauts`: This Dag shows a simple ETL pipeline example that queries the list of astronauts currently in space from the Open Notify API and prints a statement for each astronaut. The Dag uses the TaskFlow API to define tasks in Python, and dynamic task mapping to dynamically print a statement for each astronaut. For more on how this Dag works, see our [Getting started tutorial](https://www.astronomer.io/docs/learn/get-started-with-airflow).
- Dockerfile: This file contains a versioned Astro Runtime Docker image that provides a differentiated Airflow experience. If you want to execute other commands or overrides at runtime, specify them here.
- include: This folder contains any additional files that you want to include as part of your project. It is empty by default.
- packages.txt: Install OS-level packages needed for your project by adding them to this file. It is empty by default.
- requirements.txt: Install Python packages needed for your project by adding them to this file. It is empty by default.
- plugins: Add custom or community plugins for your project to this file. It is empty by default.
- airflow_settings.yaml: Use this local-only file to specify Airflow Connections, Variables, and Pools instead of entering them in the Airflow UI as you develop Dags in this project.

Deploy Your Project Locally
===========================

Start Airflow on your local machine by running 'astro dev start'.

This command will spin up five Docker containers on your machine, each for a different Airflow component:

- Postgres: Airflow's Metadata Database
- Scheduler: The Airflow component responsible for monitoring and triggering tasks
- Dag Processor: The Airflow component responsible for parsing Dags
- API Server: The Airflow component responsible for serving the Airflow UI and API
- Triggerer: The Airflow component responsible for triggering deferred tasks

When all five containers are ready the command will open the browser to the Airflow UI at http://localhost:8080/. You should also be able to access your Postgres Database at 'localhost:5432/postgres' with username 'postgres' and password 'postgres'.

Note: If you already have either of the above ports allocated, you can either [stop your existing Docker containers or change the port](https://www.astronomer.io/docs/astro/cli/troubleshoot-locally#ports-are-not-available-for-my-local-airflow-webserver).

Mubawab detail scraper
======================

The `mubawab_detail_scraper` DAG runs every 15 minutes and scrapes up to 100
pending listing detail pages per run, using one worker. It does not collect new
listing URLs; the raw listings must already exist in the scraper database.

The Airflow image installs Git from `packages.txt` and the Mubawab scraper
package from this repository's `main` branch via `requirements.txt`; the
repository must be accessible to the image builder. If the repository is
private, create `%USERPROFILE%\.netrc` outside the repository with a GitHub
token that has read-only access to the repository:

```text
machine github.com
  login YOUR_GITHUB_USERNAME
  password YOUR_GITHUB_TOKEN
```

Pass it to the image build as a BuildKit secret (from Command Prompt):

```cmd
astro dev restart --build-secret "id=netrc,src=%USERPROFILE%\.netrc"
```

Do not put the token in `requirements.txt`, the Dockerfile, or a file tracked by
Git. Rebuild and redeploy the Airflow image after changing this dependency.
Configure `MUBAWAB_DB_PATH` so the worker can read and write the same persistent
SQLite database used by the scraper. The detail pipeline will fail the Airflow
task if scraping raises an error.

Deploy Your Project to Astronomer
=================================

If you have an Astronomer account, pushing code to a Deployment on Astronomer is simple. For deploying instructions, refer to Astronomer documentation: https://www.astronomer.io/docs/astro/deploy-code/

Contact
=======

The Astronomer CLI is maintained with love by the Astronomer team. To report a bug or suggest a change, reach out to our support.

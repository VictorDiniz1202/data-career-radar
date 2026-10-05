# Data Career Radar

A robust ETL pipeline to discover and rank remote data career opportunities. 

## Overview
This project transforms public job postings from selected companies into an explainable queue of opportunities, focusing on identifying valid remote roles that match the candidate's specific residency and requirements.

## Architecture
- **Data Ingestion**: Python-based adapters (e.g., Greenhouse, Ashby).
- **Storage**: PostgreSQL with local snapshotting.
- **Normalization**: Standardizing titles, skills, countries, and remote policies.
- **Filtering & Ranking**: Rule-based engine to prioritize eligible roles.

## Requirements
- Docker and Docker Compose
- Python 3.12+
- PostgreSQL

## Getting Started
Copy `.env.example` to `.env` and configure your settings.
```bash
docker-compose up -d
```

*This README will be updated as the pipeline is implemented.*

# PostgreSQL Database Configuration
# Loads settings from .env file

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path)

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'german_vocabulary'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432'))
}

# To create the database, run:
# createdb german_vocabulary
#
# Or using psql:
# psql -U postgres
# CREATE DATABASE german_vocabulary;

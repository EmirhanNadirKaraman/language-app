# German Text Processing and Vocabulary Extraction

This script processes German text files sentence-by-sentence, extracts vocabulary using phrase_finder, filters to dictionary entries only, and stores results in both text files and PostgreSQL database.

## Features

- ✅ Merges and cleans German text (handles compound words, quotation marks)
- ✅ Filters out glossary entries and page numbers
- ✅ **Processes text sentence-by-sentence** for accurate word extraction
- ✅ Extracts vocabulary using phrase_finder's `get_words_array()`
- ✅ **Includes all words found by phrase_finder** (exact, fuzzy, and lemma matches)
- ✅ Counts word frequencies across all sentences
- ✅ **Orders results by frequency (most common first)**
- ✅ Saves results per file and combined
- ✅ Stores in PostgreSQL database with indexes
- ✅ Progress tracking with timestamps

## How It Works

1. **Text Cleaning**: Removes line numbers, page numbers, and glossary entries
2. **Sentence Segmentation**: Uses spaCy to split text into sentences
3. **Word Extraction**: For each sentence, calls `get_words_array()` from phrase_finder
   - Example: `"Ich lade morgen meine Freunde zum Essen ein"` → `['ich', 'jdn. (Akk) zu etw. einladen', 'morgen', 'mein', 'der Freund', 'zu', 'etw. (Akk) essen', 'ein']`
4. **Frequency Counting**: Counts occurrences of each word (includes exact, fuzzy, and lemma matches)
5. **Output**: Writes frequency-sorted lists to files and PostgreSQL

## Setup

### 1. Install Dependencies

```bash
pip install spacy psycopg2-binary python-dotenv
python -m spacy download de_core_news_sm
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and update with your PostgreSQL credentials:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
DB_NAME=german_vocabulary
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

**Note**: The `.env` file is in `.gitignore` and won't be committed to git.

### 3. Create Database

```bash
createdb german_vocabulary
```

Or using psql:
```sql
CREATE DATABASE german_vocabulary;
```

## Usage

### Basic Usage

```bash
python postprocessing/script.py
```

The script will automatically **skip files that have already been processed** (by checking if output files exist in `postprocessing/results/`).

### Command-Line Options

```bash
# Force reprocessing of all files (ignore existing outputs)
python postprocessing/script.py --force

# Clear the database before processing
python postprocessing/script.py --clear-db

# Use parallel processing with 4 workers (faster!)
python postprocessing/script.py --workers 4

# Disable parallel processing (slower, but uses less memory)
python postprocessing/script.py --no-parallel

# Combine options
python postprocessing/script.py --force --clear-db --workers 8
```

**Options:**
- `--force`: Reprocess all files, even if output files already exist
- `--clear-db`: Delete all entries from the database before processing
- `--workers N`: Use N parallel workers (default: CPU count)
- `--no-parallel`: Disable parallel processing (sequential mode)

## Output

### Text Files (in `postprocessing/results/`)

Each file contains:
1. **WORDS BY FREQUENCY** - Most common words first (×count)
2. **ALPHABETICAL LIST** - All words sorted A-Z with counts
3. **DETAILED VIEW** - Grouped by word type (VERB, NOUN, ADJ, etc.), sorted by frequency

Files generated:
- `{filename}_analysis.txt` - Per file results
- `ALL_FILES_combined_analysis.txt` - Combined results

### PostgreSQL Database

Table: `word_occurrences`

Columns:
- `id` - Primary key
- `file_name` - Source file name
- `phrase` - Phrase as it appears in text
- `dictionary_entry` - Dictionary form (lemma/blueprint)
- `word_type` - POS tag (VERB, NOUN, etc.)
- `match_type` - Match type (exact, exact with article)
- `frequency` - Occurrence count
- `created_at` - Timestamp

Indexes on `dictionary_entry` and `file_name` for fast queries.

## Example Queries

```sql
-- Top 20 most common words across all files
SELECT dictionary_entry, SUM(frequency) as total
FROM word_occurrences
GROUP BY dictionary_entry
ORDER BY total DESC
LIMIT 20;

-- All words from a specific file
SELECT * FROM word_occurrences
WHERE file_name = '01_chapter1.txt'
ORDER BY frequency DESC;

-- All verbs ordered by frequency
SELECT dictionary_entry, frequency
FROM word_occurrences
WHERE word_type LIKE '%VERB%'
ORDER BY frequency DESC;
```

## Notes

- Only processes files starting with '01' (configurable in script.py line 243)
- Filters to **exact dictionary matches only** - words not in your dictionary are excluded
- Database connection is optional - script continues if connection fails
- All results are sorted by frequency in descending order

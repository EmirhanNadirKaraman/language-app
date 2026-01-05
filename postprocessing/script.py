import re
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter
import psycopg2
from psycopg2.extras import execute_batch
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Add parent directory to path to import phrase_finder
sys.path.insert(0, str(Path(__file__).parent.parent))
from phrase_finder import get_words_array, nlp as phrase_finder_nlp

def log_progress(message):
    """Print progress message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def setup_database(conn, db_user):
    """Create database tables if they don't exist."""
    with conn.cursor() as cur:
        # Create table for word occurrences
        cur.execute("""
            CREATE TABLE IF NOT EXISTS word_occurrences (
                id SERIAL PRIMARY KEY,
                file_name VARCHAR(255),
                phrase TEXT,
                dictionary_entry TEXT,
                word_type VARCHAR(50),
                match_type VARCHAR(50),
                frequency INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index for faster lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dictionary_entry
            ON word_occurrences(dictionary_entry)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_name
            ON word_occurrences(file_name)
        """)

        # Grant permissions to current user
        try:
            # Use parameterized query safely for identifiers
            from psycopg2 import sql
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON TABLE word_occurrences TO {}").format(
                    sql.Identifier(db_user)
                )
            )
            cur.execute(
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE word_occurrences_id_seq TO {}").format(
                    sql.Identifier(db_user)
                )
            )
            log_progress(f"✓ Granted permissions to user: {db_user}")
        except Exception as e:
            log_progress(f"Note: Could not grant permissions: {e}")

        conn.commit()
        log_progress("✓ Database tables created/verified")

def process_text_by_sentences(merged_text, show_progress=True):
    """
    Process text sentence by sentence and extract words.
    Returns a list of all dictionary entries found.
    """
    # Split text into sentences using spaCy
    doc = phrase_finder_nlp(merged_text)

    all_words = []
    sentence_count = 0

    for sent in doc.sents:
        sentence_text = sent.text.strip()
        if len(sentence_text) > 5:  # Skip very short fragments
            sentence_count += 1
            # Get words array for this sentence
            words = get_words_array(sentence_text)
            all_words.extend(words)

    if show_progress:
        log_progress(f"  └─ Processed {sentence_count} sentences")
    return all_words

def process_single_file(file_info):
    """
    Process a single file (used for parallel processing).
    Returns (file_name, word_counts, unique_count, file_merged_text) or None if skipped.
    """
    file, output_file, force = file_info

    # Check if already processed
    if not force and output_file.exists():
        return None  # Skip this file

    # Read and clean file
    with open(file, 'r', encoding='utf-8') as f:
        lines = [line.rstrip() for line in f.readlines() if line.strip()]

        file_text_parts = []
        for line in lines:
            if line.strip().isdigit():
                continue
            if is_glossary_line(line) or is_german_glossary(line):
                continue
            cleaned_line = remove_line_numbers(line)
            if cleaned_line:
                file_text_parts.append(cleaned_line)

        if not file_text_parts:
            return None

        # Process
        file_merged_text = clean_german_flow(file_text_parts)
        all_words = process_text_by_sentences(file_merged_text, show_progress=False)
        word_counts = Counter(all_words)

        # Write to file
        unique_count = write_analysis_to_file(
            word_counts,
            output_file,
            file_merged_text,
            file.name
        )

        return (file.name, word_counts, unique_count, file_merged_text, len(lines), len(file_text_parts))

def insert_to_database(conn, word_counts, file_name):
    """Insert word frequency results into PostgreSQL database."""
    # Prepare data for insertion
    data_to_insert = []

    for word, count in word_counts.items():
        data_to_insert.append((
            file_name,
            word,  # phrase (same as dictionary_entry for this approach)
            word,  # dictionary_entry
            'DICT_ENTRY',  # word_type
            'exact',  # match_type
            count
        ))

    # Batch insert
    with conn.cursor() as cur:
        execute_batch(cur, """
            INSERT INTO word_occurrences
            (file_name, phrase, dictionary_entry, word_type, match_type, frequency)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, data_to_insert)

        conn.commit()

    return len(data_to_insert)

def is_glossary_line(text):
    """
    Detect lines that look like glossaries with multiple numbered entries.
    Example: "7 word definition - 8 word definition - 9 word definition"
    """
    # Count occurrences of " - \d+" pattern (dash followed by number)
    pattern = r'\s+-\s+\d+'
    matches = re.findall(pattern, text)
    # If there are 2+ such patterns, it's likely a glossary line
    return len(matches) >= 2

def is_german_glossary(line):
    """Detects German glossary patterns like 'Wort, das - definition'."""
    # Pattern: Word [article] - definition
    if re.search(r'\w+,\s+(der|die|das)\s+-\s+', line, re.IGNORECASE):
        return True
    # Pattern: Multiple dashes (often used in vocab lists)
    if line.count('-') >= 2 and len(line) < 100:
        return True
    return False

def remove_line_numbers(text):
    """Remove line numbers from the start of text."""
    # Remove patterns like: "1 ", "12 ", "123 ", "1. ", "1) ", etc.
    text = re.sub(r'^\s*\d{1,3}[\.\)\s]\s*', '', text)
    return text

def clean_german_flow(text_parts):
    """Specific cleaning for German compound words and spacing."""
    full_text = ' '.join(text_parts)

    # Fix 1: Handle German hyphenated compound words split by line breaks
    # Matches 'Wort-' followed by space ' ' followed by 'teil'
    # Turns "Zimmer- tür" into "Zimmertür"
    full_text = re.sub(r'(\w+)-\s+([a-zäöüß]\w+)', r'\1\2', full_text)

    # Fix 2: Standardize German quotation marks for spaCy
    full_text = full_text.replace('„', '"').replace('"', '"').replace('»', '"').replace('«', '"')

    # Fix 3: Remove extra whitespace
    full_text = re.sub(r'\s+', ' ', full_text)

    return full_text

def write_analysis_to_file(word_counts, output_file, merged_text, file_name=None):
    """Write word frequency analysis to a file with nice formatting."""
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write("="*80 + "\n")
        if file_name:
            f.write(f"EXTRACTED WORDS FROM: {file_name}\n")
        else:
            f.write("EXTRACTED WORDS FROM ALL GERMAN TEXTS\n")
        f.write("="*80 + "\n\n")
        f.write(f"Total text length: {len(merged_text)} characters\n")
        f.write(f"Total word occurrences: {sum(word_counts.values())}\n")
        f.write(f"Unique dictionary entries: {len(word_counts)}\n")
        f.write("="*80 + "\n\n")

        # MOST IMPORTANT: Write frequency-sorted list FIRST
        f.write("="*80 + "\n")
        f.write("WORDS BY FREQUENCY (Most Common First)\n")
        f.write("="*80 + "\n\n")

        for entry, count in word_counts.most_common():
            f.write(f"{entry:<60} ×{count}\n")

        # Write alphabetically sorted list
        f.write("\n" + "="*80 + "\n")
        f.write("ALPHABETICAL LIST (All Dictionary Entries)\n")
        f.write("="*80 + "\n\n")

        for entry in sorted(word_counts.keys()):
            count = word_counts[entry]
            f.write(f"{entry:<60} ×{count}\n")

    return len(word_counts)

def main():
    """Main execution function."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Process German text files and extract vocabulary')
    parser.add_argument('--force', action='store_true',
                        help='Force reprocessing of all files (skip check for existing outputs)')
    parser.add_argument('--clear-db', action='store_true',
                        help='Clear database before processing')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of parallel workers (default: CPU count)')
    parser.add_argument('--no-parallel', action='store_true',
                        help='Disable parallel processing')
    args = parser.parse_args()

    # Import database configuration
    try:
        from db_config import DB_CONFIG
    except ImportError:
        # Fallback configuration if db_config.py doesn't exist
        DB_CONFIG = {
            'dbname': 'german_vocabulary',
            'user': 'postgres',
            'password': 'postgres',
            'host': 'localhost',
            'port': 5432
        }

    FOLDER_PATH = Path('files/text')
    OUTPUT_FOLDER = Path('postprocessing/results')
    OUTPUT_FOLDER.mkdir(exist_ok=True)

    # Connect to PostgreSQL
    log_progress("Connecting to PostgreSQL database...")
    try:
        db_conn = psycopg2.connect(**DB_CONFIG)
        log_progress(f"✓ Connected to database as user: {DB_CONFIG['user']}")
        setup_database(db_conn, DB_CONFIG['user'])

        # Clear database if requested
        if args.clear_db:
            log_progress("Clearing existing database entries...")
            with db_conn.cursor() as cur:
                cur.execute("DELETE FROM word_occurrences")
                db_conn.commit()
            log_progress("✓ Database cleared")
    except Exception as e:
        log_progress(f"✗ Database connection failed: {e}")
        log_progress("Continuing without database...")
        db_conn = None

    # Count total files first
    files_to_process = [f for f in FOLDER_PATH.glob('*.txt')]
    total_files = len(files_to_process)

    log_progress(f"Found {total_files} files to process")
    log_progress("="*60)

    # Collect all text from all files and process each file individually
    all_text_parts = []

    # Determine number of workers
    if args.no_parallel:
        num_workers = 1
    else:
        num_workers = args.workers if args.workers else multiprocessing.cpu_count()

    log_progress(f"Using {num_workers} worker(s) for parallel processing")

    # Prepare file info for parallel processing
    file_infos = [(f, OUTPUT_FOLDER / f"{f.stem}_analysis.txt", args.force) for f in files_to_process]

    # Process files in parallel
    if num_workers > 1:
        log_progress("Processing files in parallel...")
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(process_single_file, info): info[0] for info in file_infos}

            # Process results as they complete
            for idx, future in enumerate(as_completed(futures), 1):
                file = futures[future]
                try:
                    result = future.result()
                    if result is None:
                        log_progress(f"[{idx}/{total_files}] Skipped {file.name} (already processed)")
                    else:
                        file_name, word_counts, unique_count, file_merged_text, lines_read, lines_cleaned = result
                        log_progress(f"[{idx}/{total_files}] ✓ {file_name}: {sum(word_counts.values())} occurrences, {unique_count} unique")

                        # Collect for combined analysis
                        all_text_parts.extend(file_merged_text.split())

                        # Insert to database
                        if db_conn:
                            inserted_count = insert_to_database(db_conn, word_counts, file_name)
                except Exception as e:
                    log_progress(f"[{idx}/{total_files}] ✗ Error processing {file.name}: {e}")
    else:
        # Sequential processing (original code)
        for idx, file in enumerate(files_to_process, 1):
            output_file = OUTPUT_FOLDER / f"{file.stem}_analysis.txt"
            if not args.force and output_file.exists():
                log_progress(f"[{idx}/{total_files}] Skipping {file.name} (already processed)")
                print()
                continue

            log_progress(f"[{idx}/{total_files}] Processing: {file.name}")

            with open(file, 'r', encoding='utf-8') as f:
                lines = [line.rstrip() for line in f.readlines() if line.strip()]
                log_progress(f"  └─ Read {len(lines)} lines")

                file_text_parts = []
                for line in lines:
                    if line.strip().isdigit():
                        continue
                    if is_glossary_line(line) or is_german_glossary(line):
                        continue
                    cleaned_line = remove_line_numbers(line)
                    if cleaned_line:
                        file_text_parts.append(cleaned_line)
                        all_text_parts.append(cleaned_line)

                log_progress(f"  └─ Cleaned to {len(file_text_parts)} valid lines")

                if file_text_parts:
                    log_progress("  └─ Merging and cleaning text...")
                    file_merged_text = clean_german_flow(file_text_parts)

                    log_progress(f"  └─ Processing sentences with phrase_finder ({len(file_merged_text)} chars)...")
                    all_words = process_text_by_sentences(file_merged_text)
                    log_progress(f"  └─ Found {len(all_words)} total word occurrences")

                    word_counts = Counter(all_words)

                    log_progress("  └─ Writing results to file...")
                    unique_count = write_analysis_to_file(
                        word_counts,
                        output_file,
                        file_merged_text,
                        file.name
                    )
                    log_progress(f"  └─ ✓ Complete: {sum(word_counts.values())} occurrences, {unique_count} unique entries")

                    if db_conn:
                        log_progress("  └─ Inserting into database...")
                        inserted_count = insert_to_database(db_conn, word_counts, file.name)
                        log_progress(f"  └─ ✓ Inserted {inserted_count} entries into database")

                    print()

    # Merge all text with German-specific cleaning and create combined analysis
    log_progress("="*60)
    log_progress("Creating combined analysis from all files...")
    log_progress("="*60)

    log_progress(f"Merging {len(all_text_parts)} text parts...")
    merged_text = clean_german_flow(all_text_parts)

    log_progress(f"Processing sentences with phrase_finder ({len(merged_text)} chars)...")
    all_words = process_text_by_sentences(merged_text)
    log_progress(f"Found {len(all_words)} total word occurrences")

    # Count frequencies (no filtering - include all words from phrase_finder)
    word_counts = Counter(all_words)

    # Write filtered combined results
    log_progress("Writing combined results...")
    combined_output = OUTPUT_FOLDER / "ALL_FILES_combined_analysis.txt"
    unique_count = write_analysis_to_file(word_counts, combined_output, merged_text)

    # Note: Combined results are NOT inserted into database (only individual files are)

    # Close database connection
    if db_conn:
        db_conn.close()
        log_progress("✓ Database connection closed")

    log_progress("="*60)
    log_progress("✓ ALL PROCESSING COMPLETE")
    log_progress("="*60)
    print("\nCombined results:")
    print(f"  → {sum(word_counts.values())} total word occurrences")
    print(f"  → {unique_count} unique dictionary entries")
    print(f"  → Saved to: {combined_output}")
    print(f"\nAll results saved to: {OUTPUT_FOLDER}/")

if __name__ == '__main__':
    main()

import pulp
import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from postprocessing
from postprocessing.db_config import DB_CONFIG

class OptimalSetFinder:
    def __init__(self, target_words_file='data/b1_parsed.txt', known_words_file='data/known_words.txt'):
        self.target_words_file = target_words_file
        self.known_words_file = known_words_file

        self.target_words = set()
        self.known_words = set()
        self.word_counts = dict()  # File word counts (used as cost/duration)
        self.file_to_words = dict()  # Maps file -> set of target words it contains

        self.load()


    def load(self):
        """Load target words, known words, and build file-to-words mapping from database."""
        # Load target words
        with open(self.target_words_file, 'r', encoding='utf-8') as f:
            self.target_words = {line.strip() for line in f if line.strip()}

        print(f"Loaded {len(self.target_words)} target words")

        # Load known words if file exists
        if os.path.exists(self.known_words_file):
            with open(self.known_words_file, 'r', encoding='utf-8') as f:
                self.known_words = {line.strip() for line in f if line.strip()}
            print(f"Loaded {len(self.known_words)} known words")

        # Remove known words from target set
        self.target_words_to_cover = self.target_words - self.known_words
        print(f"Need to cover {len(self.target_words_to_cover)} words (after excluding known words)")

        # Query database for file vocabularies
        self._load_from_database()


    def _load_from_database(self):
        """Query database for file vocabularies and word counts."""
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

        try:
            with conn.cursor() as cur:
                # Get all files and their words from the database
                cur.execute("""
                    SELECT
                        file_name,
                        dictionary_entry,
                        SUM(frequency) as total_frequency
                    FROM word_occurrences
                    GROUP BY file_name, dictionary_entry
                    ORDER BY file_name
                """)

                results = cur.fetchall()

                # Build file_to_words mapping
                for row in results:
                    file_name = row['file_name']
                    word = row['dictionary_entry']

                    # Only include words that are in our target list
                    if word in self.target_words_to_cover:
                        if file_name not in self.file_to_words:
                            self.file_to_words[file_name] = set()
                        self.file_to_words[file_name].add(word)

                # Get word counts per file (to use as cost in ILP)
                cur.execute("""
                    SELECT
                        file_name,
                        SUM(frequency) as total_words
                    FROM word_occurrences
                    GROUP BY file_name
                """)

                word_count_results = cur.fetchall()
                for row in word_count_results:
                    self.word_counts[row['file_name']] = row['total_words']

                print(f"Loaded {len(self.file_to_words)} files from database")
                print(f"Total words coverage by files: {sum(len(words) for words in self.file_to_words.values())} word-file pairs")
        finally:
            conn.close()


    def write_result_to_file(self, chosen_files, total_cost):
        """Write ILP results to output files."""
        with open('ilp/ilp_chosen_files.txt', 'w', encoding='utf-8') as f:
            for file in chosen_files:
                f.write(file + '\t' + str(self.word_counts[file]) + '\n')

            f.write(f"Total word count: {total_cost}\n")

        with open('ilp/ilp_combined_files.txt', 'w', encoding='utf-8') as f:
            for file in chosen_files:
                file_path = f'files/text/{file}'
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f2:
                        text = ' '.join([line.strip() for line in f2.readlines()])
                        f.write('=' * 80 + '\n')
                        f.write(f'FILE: {file}\n')
                        f.write('=' * 80 + '\n')
                        f.write(text + '\n\n')


    def algo(self, min_occurrences=1):
        """Run ILP optimization to find minimum set of files that cover all target words.

        Args:
            min_occurrences: Minimum number of files that must contain each word.
                           Default 1 = each word appears in at least 1 file.
                           2 = each word appears in at least 2 files (for repetition).
        """
        print("\n" + "=" * 80)
        print("RUNNING ILP OPTIMIZATION")
        print("=" * 80)
        print(f"Minimum occurrences per word: {min_occurrences}")

        # Set up the ILP problem
        prob = pulp.LpProblem("MinimizeTotalWordCount", pulp.LpMinimize)

        # Create binary variables for each file
        file_vars = {
            file: pulp.LpVariable(f"file_{file.replace('.', '_').replace(' ', '_').replace('-', '_')}", cat='Binary')
            for file in self.file_to_words
        }

        # Objective: minimize total word count across selected files
        prob += pulp.lpSum(file_vars[file] * self.word_counts[file] for file in self.file_to_words)

        # Constraints: each target word must be covered by at least min_occurrences selected files
        uncoverable_count = 0
        insufficient_files_count = 0

        for word in sorted(self.target_words_to_cover):
            covering_files = [file for file, words in self.file_to_words.items() if word in words]

            if not covering_files:
                uncoverable_count += 1
                continue

            # If word doesn't appear in enough files to meet min_occurrences requirement
            if len(covering_files) < min_occurrences:
                insufficient_files_count += 1
                # Use as many as available
                required = len(covering_files)
            else:
                required = min_occurrences

            prob += pulp.lpSum(file_vars[file] for file in covering_files) >= required, f"Cover_{word[:50]}"

        if uncoverable_count > 0:
            print(f"WARNING: {uncoverable_count} words cannot be covered by any file")

        if insufficient_files_count > 0:
            print(f"WARNING: {insufficient_files_count} words appear in fewer than {min_occurrences} files")

        # Solve the ILP
        print("\nSolving ILP problem...")
        prob.solve(pulp.PULP_CBC_CMD(msg=True, gapRel=0.08))

        # Check solution status
        status = pulp.LpStatus[prob.status]
        print(f"\nSolution Status: {status}")

        if status != 'Optimal':
            print("WARNING: Could not find optimal solution!")
            return None

        # Extract results
        self.chosen_files = [f for f in file_vars if pulp.value(file_vars[f]) == 1]
        total_word_count = sum(self.word_counts[f] for f in self.chosen_files)

        # Calculate coverage
        covered_words_count = len(self.target_words_to_cover) - uncoverable_count
        coverage_pct = (covered_words_count / len(self.target_words_to_cover)) * 100 if self.target_words_to_cover else 0

        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Chosen Files: {len(self.chosen_files)}")
        print(f"Total Word Count: {total_word_count:,}")
        print(f"Words Covered: {covered_words_count} / {len(self.target_words_to_cover)} ({coverage_pct:.2f}%)")
        print("\nFiles:")
        for file in sorted(self.chosen_files):
            print(f"  - {file} ({self.word_counts[file]:,} words)")

        self.write_result_to_file(self.chosen_files, total_word_count)

        return self.chosen_files


    def order_files(self, method='density_increasing'):
        """Order the chosen files by various methods.

        Args:
            method: Ordering method. Options:
                - 'density_increasing': Lowest to highest word density
                - 'density_decreasing': Highest to lowest word density
                - 'new_words_descending': Greedy - most new words first
                - 'target_words_descending': Most target words in file first
        """
        # Read the chosen files from the ILP output
        with open('ilp/ilp_chosen_files.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            chosen_files = [line.split('\t')[0] for line in lines if '\t' in line]

        method_names = {
            'density_increasing': 'INCREASING WORD DENSITY',
            'density_decreasing': 'DECREASING WORD DENSITY',
            'new_words_descending': 'NEW WORDS (GREEDY APPROACH)',
            'target_words_descending': 'TOTAL TARGET WORDS'
        }

        print("\n" + "=" * 80)
        print(f"ORDERING FILES BY {method_names.get(method, method.upper())}")
        print("=" * 80)

        if method in ['density_increasing', 'density_decreasing', 'target_words_descending']:
            # Calculate density and target words for each file
            file_data = []
            for file in chosen_files:
                target_words_in_file = self.target_words_to_cover & self.file_to_words.get(file, set())
                density = len(target_words_in_file) / self.word_counts[file] if self.word_counts[file] > 0 else 0
                file_data.append((file, density, len(target_words_in_file)))

            # Sort based on method
            if method == 'density_increasing':
                file_data.sort(key=lambda x: x[1])
            elif method == 'density_decreasing':
                file_data.sort(key=lambda x: x[1], reverse=True)
            elif method == 'target_words_descending':
                file_data.sort(key=lambda x: x[2], reverse=True)

            # Calculate cumulative coverage
            marked_words = set()
            result_files_detailed = []

            for idx, (file, density, total_target_words) in enumerate(file_data, 1):
                new_words = (self.target_words_to_cover - marked_words) & self.file_to_words.get(file, set())
                marked_words.update(new_words)

                result_files_detailed.append((file, new_words, len(new_words), density, total_target_words))
                print(f"{idx}. {file}: +{len(new_words)} new words (density: {density:.6f}, total target words: {total_target_words})")

            result_files = [item[0] for item in file_data]

        elif method == 'new_words_descending':
            # Greedy approach: at each step, choose file with most new words
            marked_words = set()
            result_files_detailed = []
            result_files = []
            remaining_files = set(chosen_files)

            while remaining_files:
                best_file = None
                best_new_words = set()
                best_density = 0
                best_total_target = 0

                for file in remaining_files:
                    target_words_in_file = self.target_words_to_cover & self.file_to_words.get(file, set())
                    new_words = target_words_in_file - marked_words

                    if len(new_words) > len(best_new_words):
                        best_new_words = new_words
                        best_file = file
                        best_density = len(target_words_in_file) / self.word_counts[file] if self.word_counts[file] > 0 else 0
                        best_total_target = len(target_words_in_file)

                if best_file:
                    marked_words.update(best_new_words)
                    result_files.append(best_file)
                    result_files_detailed.append((best_file, best_new_words, len(best_new_words), best_density, best_total_target))
                    remaining_files.remove(best_file)
                    print(f"{len(result_files)}. {best_file}: +{len(best_new_words)} new words (density: {best_density:.6f}, total target words: {best_total_target})")
                else:
                    break

        # Write reordered results
        output_suffix = method.replace('_', '-')
        with open(f'ilp/ilp_files_reordered_{output_suffix}.txt', 'w', encoding='utf-8') as f:
            f.write(f"OPTIMALLY ORDERED READING LIST - {method_names.get(method, method)}\n")
            f.write("=" * 80 + "\n\n")

            for idx, (file, words, new_word_count, density, total_target_words) in enumerate(result_files_detailed, 1):
                f.write(f"{idx}. {file}\n")
                f.write(f"   Density: {density:.6f}\n")
                f.write(f"   Target words in file: {total_target_words}\n")
                f.write(f"   New words added: {new_word_count}\n")
                f.write(f"   Total words in file: {self.word_counts[file]:,}\n\n")

        # Write combined file with full text
        with open('ilp/ilp_files_reordered_combined.txt', 'w', encoding='utf-8') as f:
            for idx, file in enumerate(result_files, 1):
                file_path = f'files/text/{file}'
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f2:
                        text = ' '.join([line.strip() for line in f2.readlines()])
                        f.write('=' * 80 + '\n')
                        f.write(f'{idx}. FILE: {file}\n')
                        f.write('=' * 80 + '\n')
                        f.write(text + '\n\n')

        print(f"\nOrdered {len(result_files)} files successfully!")
        return result_files


def main():
    """Main function to run ILP optimization."""
    import sys

    print("=" * 80)
    print("OPTIMAL FILE SET FINDER - ILP Approach")
    print("=" * 80)

    # Parse command line arguments
    # Usage: python optimal_set_finder.py [min_occurrences] [ordering_method]
    # Examples:
    #   python optimal_set_finder.py 2
    #   python optimal_set_finder.py 2 new_words_descending
    #   python optimal_set_finder.py

    min_occurrences = 1  # Default
    ordering_method = None

    if len(sys.argv) > 1:
        # First argument: min_occurrences (if it's a number)
        arg1 = sys.argv[1]
        if arg1.isdigit():
            min_occurrences = int(arg1)
        else:
            # If first arg is not a number, it's an ordering method
            ordering_method = arg1

    if len(sys.argv) > 2:
        # Second argument: ordering method
        ordering_method = sys.argv[2]

    try:
        # Initialize and load data
        finder = OptimalSetFinder()

        # Run ILP optimization
        result = finder.algo(min_occurrences=min_occurrences)

        if result:
            # Generate orderings
            if ordering_method:
                valid_methods = ['density_increasing', 'density_decreasing', 'new_words_descending', 'target_words_descending']
                if ordering_method not in valid_methods:
                    print(f"\nInvalid method: {ordering_method}")
                    print(f"Valid methods: {', '.join(valid_methods)}")
                    return
                finder.order_files(method=ordering_method)
            else:
                # Generate all ordering methods
                print("\nGenerating all ordering methods...")
                methods = ['new_words_descending', 'density_increasing', 'density_decreasing', 'target_words_descending']
                for method in methods:
                    finder.order_files(method=method)

            print("\n" + "=" * 80)
            print("OPTIMIZATION COMPLETE!")
            print("=" * 80)
            print("\nOutput files created:")
            print("  - ilp/ilp_chosen_files.txt (ILP solution)")
            print("  - ilp/ilp_combined_files.txt (Combined text)")
            print("  - ilp/ilp_files_reordered_new-words-descending.txt (Greedy - most new words first)")
            print("  - ilp/ilp_files_reordered_density-increasing.txt (Lowest to highest density)")
            print("  - ilp/ilp_files_reordered_density-decreasing.txt (Highest to lowest density)")
            print("  - ilp/ilp_files_reordered_target-words-descending.txt (Most target words first)")
            print("  - ilp/ilp_files_reordered_combined.txt (Combined text for last ordering)")
            print("\nUsage:")
            print("  python ilp/optimal_set_finder.py [min_occurrences] [ordering_method]")
            print("  min_occurrences: minimum files per word (default: 1)")
            print("  ordering_method: new_words_descending, density_increasing, density_decreasing, target_words_descending")
            print("\nExamples:")
            print("  python ilp/optimal_set_finder.py               # Each word in at least 1 file")
            print("  python ilp/optimal_set_finder.py 2             # Each word in at least 2 files")
            print("  python ilp/optimal_set_finder.py 2 new_words_descending")
            print("  python ilp/optimal_set_finder.py new_words_descending  # Just specify ordering")

    except psycopg2.Error as e:
        print(f"\nDatabase error: {e}")
        print("Make sure the database is running and you've processed some files.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

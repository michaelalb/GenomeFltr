import argparse
import pandas as pd
import sys
import os
from pathlib import Path

from KrakenConsts import CUSTOM_DB_TESTING_TMP_FILE

if __name__ == '__main__':
    help_text = 'Path to a valid fasta file for testing, asuumes all sequences will be classified, ' \
                'recommended to use the same one used to create if custom db'
    parser = argparse.ArgumentParser(description='Testing Kraken DB')
    parser.add_argument('--TestingFastaPath', '-TestingFastaPath', help=help_text)
    args = parser.parse_args()
    testing_output_path = str(Path(args.TestingFastaPath).parent / CUSTOM_DB_TESTING_TMP_FILE)

    testing_res = pd.read_csv(testing_output_path, sep='\t', header=None)
    testing_res.rename(columns={0: 'is_classified', 1: "read_name", 2: "classified_species", 3: "read_length",
                                4: "all_classified_K_mers"}, inplace=True)
    if 'U' in testing_res['is_classified'].unique():
        os.remove(testing_output_path)
        sys.exit(1)
    else:
        sys.exit(0)

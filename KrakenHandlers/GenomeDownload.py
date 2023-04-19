import sys
sys.path.append("/groups/pupko/alburquerque/NgsReadClearEngine")
import ncbi_genome_download as ngd
import argparse
import os
from KrakenConsts import OUTPUT_MERGED_FASTA_FILE_NAME
import glob
import gzip
import shutil


def get_file_name(taxid: str):
    return f'{taxid}.fasta'


def download_genome(output_path: str, taxid: str, acession_numbers: list):
    """Downloads the genomes of species

    Parameters
    ----------
    output_path: str
        where to download to
    taxid: str
        taxid of the speice to download (for example: "Salmon" = "8030", "e. coli" = "562")
    acession_numbers: list
        list of acession numbers to download specific genomes. This list may be **null** and thats mean download randomly.

    Returns
    -------
    int
        success code

    """
    taxid = ''.join(filter(str.isdigit, taxid))
    print(f'ngd.download(taxids={[taxid]}, flat_output=True, output={output_path}, acession_numbers={acession_numbers})')
    res = ngd.download(taxids=[taxid], flat_output=True, output=output_path, file_formats='fasta', assembly_levels='complete',acession_numbers=acession_numbers)
    print(f'res = {res}')
    if res == 0:
        print(f'donwload succesfully taxid = {taxid}')
    else:
        # trying to download not complete assemblies
        print(f'ngd.download(taxids=[{taxid}], flat_output=True, output=output_path, file_formats=fasta, acession_numbers={acession_numbers})')
        res = ngd.download(taxids=[taxid], flat_output=True, output=output_path, file_formats='fasta', acession_numbers=acession_numbers)
        print(f'res = {res}')
        if res != 0:
            return False
    return True

def unzip_file(filename):
        with gzip.open(filename, 'rb') as f_in:
            unzipped_filename = '.'.join(filename.split('.')[:-1])
            with open(unzipped_filename, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        return unzipped_filename

if __name__ == "__main__":
    CLI=argparse.ArgumentParser()
    CLI.add_argument(
      "--list_taxids",  # name on the CLI - drop the `--` for positional/required parameters
      nargs="*",  # 0 or more values expected => creates a list
      type=str,
      #default=[1, 2, 3],  # default if nothing is provided
    )
    CLI.add_argument(
      "--list_accession_number",  # name on the CLI - drop the `--` for positional/required parameters
      nargs="*",  # 0 or more values expected => creates a list
      type=str,
      #default=[1, 2, 3],  # default if nothing is provided
    )
    CLI.add_argument(
      "--download_path",  # name on the CLI - drop the `--` for positional/required parameters
      nargs="+",
      type=str,
    )
    args = CLI.parse_args()
    
    print("list_taxids: ", args.list_taxids)
    print("list_accession_number: ", args.list_accession_number)
    print("download_path: ", args.download_path)
    
    download_path = args.download_path[0]
    list_accession_number = args.list_accession_number
    # input example acc1,acc2@@acc3,acc4@@acc5 (where acc1 & acc2 are for the first speice and acc3 & acc4 for second)
    if args.list_accession_number:
        # split to list of species
        list_accession_number = args.list_accession_number[0].split('@@')
        print(f'after split @@: {list_accession_number}')
        # split the accession number
        list_accession_number = [x.split(',') for x in list_accession_number]
        print(f'after split ,: {list_accession_number}')
    
    for idx, taxaid in enumerate(args.list_taxids):
        taxaid = taxaid.replace(",", "") #some of the strings comes with ","
        print(f'downloading taxaid = {taxaid}')
        if list_accession_number and len(list_accession_number[idx]) != 0:
            res = download_genome(download_path, taxaid, list_accession_number[idx])
        else:
            res = download_genome(download_path, taxaid, [])
        if not res:
            # this will crash the process and will return error to the user
            exit()
    
    output_merged_fasta_path = os.path.join(download_path, OUTPUT_MERGED_FASTA_FILE_NAME)
    with open(output_merged_fasta_path, 'w') as out_file:
        for downloaed_file in glob.glob(f'{download_path}/*_genomic.fna.gz'):
            genome_fasta_path = unzip_file(downloaed_file)
            with open(genome_fasta_path, 'r') as in_file:
                for line in in_file:
                    out_file.write(line)
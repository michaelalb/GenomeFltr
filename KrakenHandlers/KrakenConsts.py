from pathlib import Path

# todo replace all paths
CODE_BASE_PATH = Path("/groups/pupko/alburquerque/NgsReadClearEngine/")
BASE_PATH_TO_KRAKEN_SCRIPT = Path("/groups/pupko/alburquerque/Kraken/")
PATH_TO_DB_VALIDATOR_SCRIPT = Path("/groups/pupko/alburquerque/NgsReadClearEngine/KrakenHandlers/DbTestingScript.py")
PATH_TO_CUSTOM_GENOME_DOWNLOAD_SCRIPT = Path("/groups/pupko/alburquerque/NgsReadClearEngine/KrakenHandlers/GenomeDownload.py")
KRAKEN_SEARCH_SCRIPT_COMMAND = str(BASE_PATH_TO_KRAKEN_SCRIPT) + "/kraken2"
KRAKEN_CUSTOM_DB_SCRIPT_COMMAND = str(BASE_PATH_TO_KRAKEN_SCRIPT) + "/kraken2-build"
OUTPUT_MERGED_FASTA_FILE_NAME = f'merged.fasta'

# assuming the DB is in the same BASE folder as the kraken script
KRAKEN_DB_NAMES = {
                    'Bacteria': "RefSeq complete bacterial genomes",
                    'human': "GRCh38 human genome",
                    'fungi': "RefSeq complete fungal genomes",
                    'protozoa': "RefSeq complete protozoan genomes",
                    'UniVec': "NCBI-supplied database of vector, adapter, linker, and primer sequences that may be contaminating sequencing projects and/or assemblies",
                    'plasmid': "RefSeq plasmid nucleotide sequences",
                    'archaea': "RefSeq complete archaeal genomes",
                    'Viral': "RefSeq complete viral genomes",
                    'Kraken Standard': "complete genomes in RefSeq for the bacterial, archaeal, and viral domains, along with the human genome and a collection of known vectors (UniVec_Core)."
                  }
KRAKEN_RESULTS_FILE_PATH = BASE_PATH_TO_KRAKEN_SCRIPT / "Temp_Job_{job_unique_id}_results.txt"

# Kraken Search Job variables
KRAKEN_JOB_QUEUE_NAME = 'lifesciweb'
NUBMER_OF_CPUS_KRAKEN_SEARCH_JOB = '10'
KRAKEN_JOB_PREFIX = 'KR'
KRAKEN_CUSTOM_DB_JOB_PREFIX = 'CDB'
KRAKEN_CUSTOM_DB_NAME_PREFIX = 'CustomDB_'
CUSTOM_DB_TESTING_TMP_FILE = 'CustomDbTestingRes.txt'
KRAKEN_DB_MEM_REQS = {
    'Bacteria': 60,
    'human': 30,
    'fungi': 40,
    'protozoa': 25,
    'UniVec': 25,
    'plasmid': 25,
    'archaea': 25,
    'Viral': 25,
    'Kraken Standard': 60
}
CREATE_FILE_FOR_POST_PROCESS_COMMAND = "cat {query_path} | seqkit grep -f {ids_list}  -o {ids_results}\n"

KRAKEN_JOB_TEMPLATE = '''
#!/bin/bash

#PBS -S /bin/bash
#PBS -r y
#PBS -q {queue_name}
#PBS -l ncpus={cpu_number}
#PBS -l mem={mem_req}gb
#PBS -v PBS_O_SHELL=bash,PBS_ENVIRONMENT=PBS_BATCH
#PBS -N {job_name}
#PBS -e {error_files_path}
#PBS -o {output_files_path}

source /powerapps/share/miniconda3-4.7.12/etc/profile.d/conda.sh
conda activate NGScleaner
cd {kraken_base_folder}
PYTHONPATH=$(pwd)

sleep {sleep_interval}

{kraken_command} --db "{db_path}" "{query_path_string}" --output "{kraken_results_path}" --threads 20 --use-names --report "{report_file_path}" {additional_parameters}
python {path_to_output_processor} --outputFilePath "{kraken_results_path}"

{create_files_for_post_process_commands}

#rm {query_path}
'''

# Kraken Custom Db Creation
KRAKEN_CUSTOM_DB_JOB_TEMPLATE = '''
#!/bin/bash

#PBS -S /bin/bash
#PBS -r y
#PBS -q {queue_name}
#PBS -l ncpus={cpu_number}
#PBS -v PBS_O_SHELL=bash,PBS_ENVIRONMENT=PBS_BATCH
#PBS -N {job_name}
#PBS -e {error_files_path}
#PBS -o {output_files_path}

source /powerapps/share/miniconda3-4.7.12/etc/profile.d/conda.sh
conda activate NGScleaner
#source /groups/pupko/alburquerque/miniconda3/etc/profile.d/conda.sh
#conda activate RLworkshop

PYTHONPATH=$(pwd)

python {path_to_genome_download_script} --download_path {path_to_user_base_folder} --list_accession_number {list_of_accession_numbers} --list_taxids {list_of_taxaids}

DB_NAME="{kraken_base_folder}{custom_db_name}"

for i in 1,2,3
do

    rm -r -f $DB_NAME
    
    mkdir $DB_NAME
    
    #/groups/pupko/alburquerque/Kraken/kraken2-build --db $DB_NAME --download-taxonomy --fast-build --threads {cpu_number}
    
    mkdir $DB_NAME/taxonomy
    
    cp -R "{kraken_base_folder}Tax_Base/taxonomy/." $DB_NAME/taxonomy
    
    {kraken_db_command} --db $DB_NAME -add-to-library "{path_to_fasta_file}"
    
    {kraken_db_command} --db $DB_NAME --build --fast-build --threads {cpu_number}
    
    {kraken_db_command} --db $DB_NAME --clean --fast-build --threads {cpu_number}
    
    {kraken_run_command} --db /groups/pupko/alburquerque/Kraken/{custom_db_name} "{path_to_fasta_file}" --output "{testing_output_path}" --threads {cpu_number}
    
    python {path_to_validator_script} --TestingFastaPath "{testing_output_path}" 
    exit_code=$?
    if [[ $exit_code = 1 ]]; then
        echo "Broken";
        break;
    fi
      
done

'''


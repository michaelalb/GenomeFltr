import pathlib
import subprocess
from subprocess import PIPE
import os
from utils import logger
from KrakenHandlers.KrakenConsts import BASE_PATH_TO_KRAKEN_SCRIPT, KRAKEN_SEARCH_SCRIPT_COMMAND, KRAKEN_DB_NAMES, \
    KRAKEN_JOB_TEMPLATE, KRAKEN_JOB_QUEUE_NAME, NUBMER_OF_CPUS_KRAKEN_SEARCH_JOB, KRAKEN_JOB_PREFIX, CODE_BASE_PATH, \
    KRAKEN_CUSTOM_DB_NAME_PREFIX, CREATE_FILE_FOR_POST_PROCESS_COMMAND, KRAKEN_DB_MEM_REQS
from SharedConsts import PATH_TO_OUTPUT_PROCESSOR_SCRIPT, RESULTS_SUMMARY_FILE_NAME, INPUT_CLASSIFIED_FILE_NAME, \
    INPUT_UNCLASSIFIED_FILE_NAME, TEMP_CLASSIFIED_IDS, TEMP_UNCLASSIFIED_IDS, INTERVAL_BETWEEN_LISTENER_SAMPLES, \
    INPUT_CLASSIFIED_FILE_NAME_PAIRED, INPUT_UNCLASSIFIED_FILE_NAME_PAIRED


class SearchEngine:
    """
    a class holding all code related to running the kraken2 search - assumes all inputs are valid
    """

    @staticmethod
    def kraken_search(input_path, run_parameters, db_name='Bacteria'):
        """
        this function actually preforms the kraken2 search
        :param input_path: path to input query file
        :param run_parameters: a dictionary with the kraken run parameters
        :param db_name: name of the database to run on.
        The name must be either on the standard db list or a result from the custom db creator
        :return: created job id, path to results
        """
        # create the job
        if isinstance(input_path, str):
            input_path_parent = pathlib.Path(input_path).parent
        elif isinstance(input_path, list):
            input_path_parent = pathlib.Path(input_path[0]).parent
        else:
            raise ValueError('Input file path parameter was not a list of a string')
        job_unique_id = str(input_path_parent.stem)
        temp_script_path = input_path_parent / f'temp_kraken_search_running_file_{job_unique_id}.sh'
        results_file_path = input_path_parent / 'results.txt'
        report_path = input_path_parent / RESULTS_SUMMARY_FILE_NAME
        temp_script_text = SearchEngine._create_kraken_search_job_text(input_path, run_parameters,
                                                                       job_unique_id, results_file_path,
                                                                       report_path, db_name)

        # run the job
        with open(temp_script_path, 'w+') as fp:
            fp.write(temp_script_text)
        logger.info(f'submitting job, temp_script_path = {temp_script_path}:')
        logger.debug(f'{temp_script_text}')
        terminal_cmd = f'/opt/pbs/bin/qsub {str(temp_script_path)}'
        job_run_output = subprocess.run(terminal_cmd, stdout=PIPE, stderr=PIPE, shell=True)
        # os.remove(temp_script_path)
        
        return job_run_output.stdout.decode('utf-8').split('.')[0], results_file_path

    @staticmethod
    def _create_kraken_search_job_text(query_path, run_parameters, job_unique_id, result_path, report_path, db_name):
        """
        this function creates the text for the .sh file that will run the job - assumes everything is valid
        :param query_path: path to the query file ( or list of two in the case of paired end reads)
        :param run_parameters: additional run parameters
        :param job_unique_id: the jobs unique id (used to identify everything related to this run)
        :param result_path: where to put the kraken results
        :param report_path: where to put the kraken results report
        :param db_name: name of the database to run on.
        :return: the text for the .sh file
        """
        paired_param_string = None
        files_for_pp_string = ''
        if isinstance(query_path, str):
            query_path_parent = pathlib.Path(query_path).parent
            query_path_string = query_path
        else:
            query_path_parent = pathlib.Path(query_path[0]).parent
            classified_input_path = query_path_parent / INPUT_CLASSIFIED_FILE_NAME
            unclassified_input_path = query_path_parent / INPUT_UNCLASSIFIED_FILE_NAME
            if len(query_path) == 1:
                query_path_string = query_path[0]
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[0],
                                                                                   ids_list=result_path.parent / TEMP_CLASSIFIED_IDS,
                                                                                   ids_results=classified_input_path)
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[0],
                                                                                   ids_list=result_path.parent / TEMP_UNCLASSIFIED_IDS,
                                                                                   ids_results=unclassified_input_path)
            elif len(query_path) == 2:
                query_path_string = str(query_path[0]) + '" "' + str(query_path[1])
                paired_param_string = '--paired'
                classified_input_path_paired = query_path_parent / INPUT_CLASSIFIED_FILE_NAME_PAIRED
                unclassified_input_path_paired = query_path_parent / INPUT_UNCLASSIFIED_FILE_NAME_PAIRED
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[0],
                                                                                   ids_list=result_path.parent / TEMP_CLASSIFIED_IDS,
                                                                                   ids_results=classified_input_path)
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[0],
                                                                                   ids_list=result_path.parent / TEMP_UNCLASSIFIED_IDS,
                                                                                   ids_results=unclassified_input_path)
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[1],
                                                                                   ids_list=result_path.parent / TEMP_CLASSIFIED_IDS,
                                                                                   ids_results=classified_input_path_paired)
                files_for_pp_string += CREATE_FILE_FOR_POST_PROCESS_COMMAND.format(query_path=query_path[1],
                                                                                   ids_list=result_path.parent / TEMP_UNCLASSIFIED_IDS,
                                                                                   ids_results=unclassified_input_path_paired)
            else:
                raise ValueError('too many paths passed')

        run_parameters_string = SearchEngine._create_parameter_string(run_parameters)
        if paired_param_string is not None:
            run_parameters_string += paired_param_string
        job_name = f'{KRAKEN_JOB_PREFIX}_{job_unique_id}'
        kraken_run_command = BASE_PATH_TO_KRAKEN_SCRIPT / KRAKEN_SEARCH_SCRIPT_COMMAND
        db_name, mem_req = SearchEngine._db_names_handler(db_name)
        db_path = BASE_PATH_TO_KRAKEN_SCRIPT / db_name
        job_logs_path = str(query_path_parent) + '/'

        return KRAKEN_JOB_TEMPLATE.format(queue_name=KRAKEN_JOB_QUEUE_NAME,
                                          cpu_number=NUBMER_OF_CPUS_KRAKEN_SEARCH_JOB, job_name=job_name,
                                          error_files_path=job_logs_path,
                                          output_files_path=job_logs_path,
                                          kraken_base_folder=CODE_BASE_PATH,
                                          kraken_command=kraken_run_command, db_path=db_path,
                                          query_path_string=query_path_string,
                                          query_path=query_path[0],
                                          kraken_results_path=result_path,
                                          path_to_output_processor=str(PATH_TO_OUTPUT_PROCESSOR_SCRIPT),
                                          additional_parameters=run_parameters_string,
                                          report_file_path=report_path,
                                          create_files_for_post_process_commands=files_for_pp_string,
                                          sleep_interval=INTERVAL_BETWEEN_LISTENER_SAMPLES,
                                          mem_req=mem_req)

    @staticmethod
    def _create_parameter_string(run_parameters):
        if not run_parameters:
            return ''
        parameter_string_arr = [str(param_name) + ' ' + str(param_value) + ' ' for
                                param_name, param_value in run_parameters.items()]
        return '--' + ' --'.join(parameter_string_arr)

    @staticmethod
    def _db_names_handler(name):
        # if the db is not a custom one but the name is some error
        mem_req = 10
        if name.find(KRAKEN_CUSTOM_DB_NAME_PREFIX) == -1:
            assert name in KRAKEN_DB_NAMES
            mem_req = KRAKEN_DB_MEM_REQS.get(name)
        if name == 'Kraken Standard':
            return 'BasicDB', mem_req
        return name, mem_req

# if __name__ == '__main__':
#     SearchEngine().kraken_search(["/groups/pupko/alburquerque/Kraken/TestPaired/CodeTest/TEST_MXB_R1.fastq",
#                                   "/groups/pupko/alburquerque/Kraken/TestPaired/CodeTest/TEST_MXB_R2.fastq"], None, db_name='Viral')
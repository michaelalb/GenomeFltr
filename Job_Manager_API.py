import os
import shutil
import uuid
import json
import pandas as pd
from InputValidator import InputValidator
from Job_Manager_Thread_Safe_GenomeFltr import Job_Manager_Thread_Safe_GenomeFltr
from utils import send_email, logger, LOGGER_LEVEL_JOB_MANAGE_API
from KrakenHandlers.KrakenConsts import KRAKEN_CUSTOM_DB_NAME_PREFIX, KRAKEN_JOB_PREFIX
from SharedConsts import K_MER_COUNTER_MATRIX_FILE_NAME, \
    FINAL_OUTPUT_FILE_NAME, FINAL_OUTPUT_ZIPPED_BOTH_FILES, KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME, EMAIL_CONSTS, UI_CONSTS, CUSTOM_DB_NAME, State, POSTPROCESS_JOB_PREFIX, GENOME_DOWNLOAD_SUMMARY_RESULTS_FILE_NAME, FINAL_OUTPUT_FILE_CONTAMINATED_NAME, FINAL_OUTPUT_ZIPPED_BOTH_FILES_NEW_CONTAMINATED
logger.setLevel(LOGGER_LEVEL_JOB_MANAGE_API)


class Job_Manager_API:
    """
    A class used to connect the __init__ to the backend.

    ...

    Attributes
    ----------
    

    Methods
    -------
    implemented below
    """
    def __init__(self, max_number_of_process: int, upload_root_path: str, input_file_names: list, func2update_html):
        """Creates the Job_Manager_API instances

        Parameters
        ----------
        max_number_of_process : int
            Max number of process that can run simultaneously
        upload_root_path: str
            A path to the saved files. Each process in there creates it's own folder
        input_file_names: lst
            The names of the input files (the file which the user uploaded). This is a list as 1 or 2 files might be uploaded
        func2update_html: function
            What function should be called once the state is updated

        Returns
        -------
        manager: Job_Manager_API
            instance of Job_Manager_API
        """
        self.__input_file_name = input_file_names[0]
        self.__input_file_name2 = input_file_names[1]
        self.__upload_root_path = upload_root_path
        self.__j_manager = Job_Manager_Thread_Safe_GenomeFltr(max_number_of_process, upload_root_path, input_file_names, self.__update_download_process,
                                                             self.__process_state_changed, self.__process_state_changed)
        self.input_validator = InputValidator() # creates the input_validator
        self.__func2update_html = func2update_html
        self.EXAMPLE_FOLDER_PATH = r'/data/www/flask/fltr_backend/example_process_results/'

    def __build_and_send_mail(self, process_id, subject, content, email_address):
        """Sends mail to user

        Parameters
        ----------
        process_id : str
            The ID of the process
        subject: str
            email subject
        content: str
            email content
        email_address: str
            where to send the email

        Returns
        -------
        """
        if email_address == '':
            logger.info('mail is empty, not sending')
            return
        try:
            # the emails are sent from 'TAU BioSequence <bioSequence@tauex.tau.ac.il>'
            send_email('mxout.tau.ac.il', 'TAU BioSequence <bioSequence@tauex.tau.ac.il>',
                       email_address, subject=subject,
                       content= content)
            logger.info(f'sent email to {email_address}')
        except:
            logger.exception(f'failed to sent email to {email_address}')
            
    def __update_download_process(self, process_id, state, email_address, job_name, job_prefix):
        """When the download process state is changed, this function is called.
        It will start a kraken process if the download process is finished.
        This update the __init__ by calling the __func2update_html.

        Parameters
        ----------
        process_id : str
            The ID of the process
        state: State (Enum)
            the new state of the process
        email_address: str
            where to send the email
        job_name: str
            The job name (optional) inserted by the user
        job_prefix: str
            To distinguish between processes types

        Returns
        -------
        """
        if state == State.Finished:
            logger.info(f'process_id = {process_id} state = {state}')
            # if the db is "custom" you need to add the process_id to the type of the db
            self.__j_manager.add_kraken_process(process_id, email_address, job_name, KRAKEN_CUSTOM_DB_NAME_PREFIX + process_id)
        elif state == State.Crashed:
            logger.info(f'process_id = {process_id} state = {state}')
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_CRASHED_DOWNLOAD_PROCESS.format(process_id=process_id), email_address)
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_CRASHED_DOWNLOAD_PROCESS.format(process_id=process_id) + f'\n\nemail adress of the user: {email_address}', 'edodotan@mail.tau.ac.il')
        elif state == State.Running:
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), f'Process id {process_id} have **Running**\n\nemail adress of the user: {email_address}', 'edodotan@mail.tau.ac.il')
        self.__func2update_html(process_id, state)

    def __process_state_changed(self, process_id, state, email_address, job_name, job_prefix):
        """When the process state is changed, this function is called (this funciton is called for the Kraken and post process types).

        Parameters
        ----------
        process_id : str
            The ID of the process
        state: State (Enum)
            the new state of the process
        email_address: str
            where to send the email
        job_name: str
            The job name (optional) inserted by the user
        job_prefix: str
            To distinguish between processes types

        Returns
        -------
        """
        if state == State.Crashed:
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), f'Process id {process_id} have **crashed**\n\nemail adress of the user: {email_address}', 'edodotan@mail.tau.ac.il')
        elif state == State.Running:
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), f'Process id {process_id} have **Running**\n\nemail adress of the user: {email_address}', 'edodotan@mail.tau.ac.il')
            
        if email_address != None:
            # sends mail once the job finshed or crashes
            if state == State.Finished:
                if job_prefix == KRAKEN_JOB_PREFIX:
                    self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_KRAKEN_SEARCH.format(process_id=process_id), email_address)
                elif job_prefix == POSTPROCESS_JOB_PREFIX:
                    self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_POST_PROCESS.format(process_id=process_id), email_address)
            elif state == State.Crashed:
                if job_prefix == KRAKEN_JOB_PREFIX:
                    self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_CRASHED_KRAKEN_SEARCH.format(process_id=process_id), email_address)
                elif job_prefix == POSTPROCESS_JOB_PREFIX:
                    self.__build_and_send_mail(process_id, EMAIL_CONSTS.create_title(state, job_name), EMAIL_CONSTS.CONTENT_CRASHED_POST_PROCESS.format(process_id=process_id), email_address)
            # sends mail if the genome download process crashed is on a differnt function (this function isn't called for genome download)
        else:
            logger.warning(f'process_id = {process_id} email_address is None, state = {state}, job_name = {job_name}')
        self.__func2update_html(process_id, state)

    def __delete_folder(self, process_id):
        """Deletes folder.
        Used when the file isn't valid

        Parameters
        ----------
        process_id : str
            The ID of the process

        Returns
        -------
        """
        logger.info(f'process_id = {process_id}')
        folder2remove = os.path.join(self.__upload_root_path, process_id)
        shutil.rmtree(folder2remove)

    def __find_file_path(self, file2check):
        """finds if the file exists (zip or unzipped)

        Parameters
        ----------
        file2check : str
            The path of the file to check

        Returns
        -------
        path_of_file: str
           Returns the path of the file if exists, else False
        """
        if os.path.isfile(file2check):
            return file2check
        file2check += '.gz' #maybe it is zipped
        if os.path.isfile(file2check):
            return file2check
        return False
        
    def __validate_input_file(self, process_id):
        """validate input file by testing the file itself.
        Will ungzip file if needed

        Parameters
        ----------
        process_id : str
            The ID of the process

        Returns
        -------
        is_valid: bool
            True if the file is valid, else False.
        """
        parent_folder = os.path.join(self.__upload_root_path, process_id)
        if not os.path.isdir(parent_folder):
            logger.warning(f'process_id = {process_id} doen\'t have a dir')
            return False
        file2check = os.path.join(parent_folder, self.__input_file_name)
        file2check = self.__find_file_path(file2check)
        file2check2 = os.path.join(parent_folder, self.__input_file_name2) # for paired reads
        file2check2 = self.__find_file_path(file2check2)
        # test file in the input_validator
        if not file2check2: # not paired reads
            if file2check and self.input_validator.validate_input_file(file2check):
                return True
        else:
            if file2check and self.input_validator.validate_input_file(file2check) and self.input_validator.validate_input_file(file2check2):
                return True
        self.__delete_folder(process_id)
        if not file2check2:
            logger.warning(f'validation failed {file2check}, deleting folder')
        else:
            logger.warning(f'validation failed file1: {file2check} file2: {file2check2}, deleting folder')
        return False
        
    def __validate_email_address(self, email_address):
        """validate email address.

        Parameters
        ----------
        email_address : str
            email address

        Returns
        -------
        is_valid: bool
            True if the email_address is valid, else False.
        """
        #TOOD this is a simple validation, might be better to change it
        if len(email_address) > 100:
            return False
        if '@' in email_address and '.' in email_address:
            return True
        if '' == email_address:
            return True
        return False

    def get_new_process_id(self):
        """generates a new process id

        Parameters
        ----------

        Returns
        -------
        process_id: str
            a random process_id
        """
        return str(uuid.uuid4())

    def add_kraken_process(self, process_id: str, email_address: str, job_name: str, db_type: str, species2download: list, list_accession_numbers: list):
        """Creates a new kraken process based on the user parameters

        Parameters
        ----------
        process_id: str
            The ID of the process
        email_address: str
            email adress
        job_name: str
            The job name (optional) inserted by the user
        db_type: str
            The database that the kraken will search against
        species2download: list
            list of species to download if the database type is "custom"
        list_accession_numbers: list
            for each speice you may insert specific accession numbers to download
        
        Returns
        -------
        is_process_added: bool
            True if the process has been added, else False
        """
        logger.info(f'process_id = {process_id} email_address = {email_address} db_type = {db_type} job_name = {job_name} species2download = {species2download}, list_accession_numbers = {list_accession_numbers}')
        is_valid_email = self.__validate_email_address(email_address)
        # validating file and email
        if is_valid_email:
            logger.info(f'email address')
            # adding download_genome process if the database type is "custom"
            if db_type == CUSTOM_DB_NAME:
                if not list_accession_numbers:
                    list_accession_numbers = [[] for x in species2download] #list of empty list if nothing has been asked
                self.__j_manager.add_download_process(process_id, email_address, job_name, species2download, list_accession_numbers)
                self.__build_and_send_mail(process_id, EMAIL_CONSTS.SUBMITTED_TITLE.format(job_name=job_name), EMAIL_CONSTS.SUBMITTED_CONTENT.format(process_id=process_id), email_address)
                return True
            # adding the kraken process
            self.__j_manager.add_kraken_process(process_id, email_address, job_name, db_type)
            self.__build_and_send_mail(process_id, EMAIL_CONSTS.SUBMITTED_TITLE.format(job_name=job_name), EMAIL_CONSTS.SUBMITTED_CONTENT.format(process_id=process_id), email_address)
            return True
        logger.warning(f'process_id = {process_id}, can\'t add process: is_valid_email = {is_valid_email}')
        return False
        
    def add_postprocess(self, process_id: str, species_list: list, k_threshold: float):
        """Creates a new post process based on the user parameters

        Parameters
        ----------
        process_id: str
            The ID of the process
        species_list: list
            what speceis are filtered from the reads
        k_threshold: float
            what threshold should reads be filtered from
        
        Returns
        -------
        is_process_added: bool
            True if the process has been added, else None
        """
        parent_folder = os.path.join(self.__upload_root_path, process_id)
        if os.path.isdir(parent_folder):
            self.__j_manager.add_postprocess(process_id, k_threshold, species_list)
            return True
        logger.warning(f'process_id = {process_id} don\'t have a folder')
        return None
        
    def export_file(self, process_id: str):
        """After the post process has finished (and the user already filtred his reads), this will return the path to the result file

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        filtered_file: str
            Path to the filtered result file, or None if file doesn't exists
        contaminated_file: str
            Path to the contaminated result file, or None if file doesn't exists
        """
        parent_folder = os.path.join(self.__upload_root_path, process_id)
        filtered_file = None
        contaminated_file = None
        if os.path.isdir(parent_folder):
            # try the result of one file
            filtered_file_single = os.path.join(parent_folder, FINAL_OUTPUT_FILE_NAME)
            if os.path.isfile(filtered_file_single):
                filtered_file = filtered_file_single
            # try the result of paired files
            else:
                filtered_file_zipped = os.path.join(parent_folder, FINAL_OUTPUT_ZIPPED_BOTH_FILES)
                if os.path.isfile(filtered_file_zipped):
                    filtered_file = filtered_file_zipped
            
            # try the contmianted of one file
            contaminated_file_single = os.path.join(parent_folder, FINAL_OUTPUT_FILE_CONTAMINATED_NAME)
            if os.path.isfile(contaminated_file_single):
                contaminated_file = contaminated_file_single
            # try the result of paired files
            else:
                contaminated_file_zipped = os.path.join(parent_folder, FINAL_OUTPUT_ZIPPED_BOTH_FILES_NEW_CONTAMINATED)
                if os.path.isfile(contaminated_file_zipped):
                    contaminated_file = contaminated_file_zipped
            
        if filtered_file == None:
            logger.warning(f'process_id = {process_id} doen\'t have a filtered result file')
        if contaminated_file == None:
            logger.warning(f'process_id = {process_id} doen\'t have a contaminated result file')
        return filtered_file, contaminated_file
    
    def get_kraken_job_state(self, process_id):
        """Given process_id returns the kraken process state

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        """
        return self.__j_manager.get_kraken_job_state(process_id)
    
    def get_download_job_state(self, process_id):
        """Given process_id returns the download process state

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        """
        return self.__j_manager.get_download_job_state(process_id)
    
    def get_postprocess_job_state(self, process_id):
        """Given process_id returns the post process state

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        """
        return self.__j_manager.get_postprocess_job_state(process_id)
        
    def get_UI_matrix(self, process_id):
        """Returns the matrix of the reads (this will be used in the results page).
        A short processing is done on the matrix before returning it to the __init__.
        The summary of the kraken process is added here to.

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        """
        parent_folder = os.path.join(self.__upload_root_path, process_id)
        csv_UI_matrix_path = os.path.join(parent_folder, K_MER_COUNTER_MATRIX_FILE_NAME)
        summary_stats_json_path = os.path.join(parent_folder, KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME)
        genome_download_summary_path = os.path.join(parent_folder, GENOME_DOWNLOAD_SUMMARY_RESULTS_FILE_NAME)
        df2return = None
        json2return = {}
        if os.path.isfile(csv_UI_matrix_path):
            df2return = pd.read_csv(csv_UI_matrix_path,index_col=0)
            columns = df2return.columns
            new_columns = {column:column.replace("'","") for column in columns} #columns names cannot have ' inside - causes bugs in HTML
            df2return.rename(columns=new_columns, inplace=True)
        #if os.path.isfile(summary_stats_json_path):
        #    json2return = json.load(open(summary_stats_json_path))
        else:
            logger.warning(f'process_id = {process_id} summary json not available')
        if os.path.isfile(genome_download_summary_path):
            with open(genome_download_summary_path, 'r') as f:
                for line in f.readlines():
                    speice_name, species_genomes = line.split(":")
                    title = f'Genomes  ID of {speice_name}'
                    json2return[title] = [species_genomes.replace(',', '\n'), UI_CONSTS.HELP_TEXT_TAXA_DOWNLOAD]
        
        job_name = self.__j_manager.get_job_name(process_id)
        logger.info(f'process_id = {process_id} df2return = {df2return} json2return = {json2return} job_name = {job_name}')
        # if job_name = '' then user didn't insert job name
        # if job_name = None then the process id not in the dict (but the results may be available)
        if job_name != None and job_name != '':
            # insert job_name to the json2return which will be displayed later
            json2return["job_name"] = [job_name, UI_CONSTS.HELP_TEXT_JOB_NAME]
        return df2return, json2return
    
    def add_example_postprocess(self, process_id: str, species_list: list, k_threshold: float):
        """Example postprocess to support the button on the EXAMPLE PAGE ONLY
        because this process hasn't run KRAKEN process we need to add the email and job name

        Parameters
        ----------
        process_id: str
            The ID of the process
        species_list: list
            what speceis are filtered from the reads
        k_threshold: float
            what threshold should reads be filtered from
        
        Returns
        -------
        is_process_added: bool
            True if the process has been added, else None
        """
        parent_folder = os.path.join(self.__upload_root_path, process_id)
        if os.path.isdir(parent_folder):
            self.__j_manager.add_example_postprocess(process_id, '', '',k_threshold, species_list)
            return True
        logger.warning(f'process_id = {process_id} don\'t have a folder')
        return None
    
    def copy_example_folder(self, process_folder):
        shutil.copytree(self.EXAMPLE_FOLDER_PATH, process_folder)
        
    def get_UI_example_matrix(self):
        """Returns the matrix for the **EXAMPLE** only! of the reads (this will be used in the results page).
        A short processing is done on the matrix before returning it to the __init__.
        The summary of the kraken process is added here to.

        Parameters
        ----------
        process_id: str
            The ID of the process
        
        Returns
        -------
        """
        csv_UI_matrix_path = os.path.join(self.EXAMPLE_FOLDER_PATH, 'CounterMatrixForUI.csv')
        example_input_file = os.path.join(self.EXAMPLE_FOLDER_PATH, 'reads.fasta.gz')
        df2return = None
        json2return = {}
        if os.path.isfile(csv_UI_matrix_path):
            df2return = pd.read_csv(csv_UI_matrix_path,index_col=0)
            columns = df2return.columns
            new_columns = {column:column.replace("'","") for column in columns} #columns names cannot have ' inside - causes bugs in HTML
            df2return.rename(columns=new_columns, inplace=True)
        #if os.path.isfile(summary_stats_json_path):
        #    json2return = json.load(open(summary_stats_json_path))
        
        job_name = 'EXAMPLE'
        # if job_name = '' then user didn't insert job name
        # if job_name = None then the process id not in the dict (but the results may be available)
        if job_name != None and job_name != '':
            # insert job_name to the json2return which will be displayed later
            json2return["job_name"] = [job_name, UI_CONSTS.HELP_TEXT_JOB_NAME]
        logger.info(f'example page, df2return = {df2return} json2return = {json2return} job_name = {job_name}, example_input_file = {example_input_file}')
        return df2return, json2return, example_input_file
    
    def parse_form_inputs(self, form_dict: dict):
        """Parse the form of the user.

        Parameters
        ----------
        form_dict: dict
            The from from the request of the user
        
        Returns
        -------
        email_address: str
            user email adress
        db_type: str
            database type to search against
        job_name: str
            the name of the job, inserted by user (optional), if None is inserted then a empty string will be returned
        species_list: list
            species list to download if database is "CUSTOM"
        accession_list: list
            this will be list of list to download specific genomes. For example: [[acc1, acc2],[],[acc3]] the first list refer to accession number of the first speices and so one (the empty list refer to the second speice)
        """
        email_address = form_dict.get('email', None)
        job_name = form_dict.get('job_name', "")
        db_type = form_dict.get('db', CUSTOM_DB_NAME)
        species_list = []
        accession_list = []
        if db_type == CUSTOM_DB_NAME:
            for i in range(UI_CONSTS.KRAKEN_MAX_CUSTOM_SPECIES):
                species_input = form_dict.get(UI_CONSTS.SPECIES_FORM_PREFIX + str(i), '')
                if species_input != '':
                    species_list.append(species_input)
            for i in range(UI_CONSTS.KRAKEN_MAX_CUSTOM_SPECIES):
                accession_list_of_specie_i = []
                for j in range(UI_CONSTS.KRAKEN_MAX_CUSTOM_SPECIES):
                    accession_input_i_j = form_dict.get(f'{UI_CONSTS.ACCESSION_FORM_PREFIX}_{i}_{j}', '')
                    if accession_input_i_j != '':
                        accession_list_of_specie_i.append(accession_input_i_j)
                accession_list.append(accession_list_of_specie_i)
        return email_address, db_type, job_name, species_list, accession_list
        
    def valid_species_list(self, species_list: list):
        """valid species list.
        This should valid the speceis list before starting the process itself.

        Parameters
        ----------
        form_dict: dict
            The from from the request of the user
        
        Returns
        -------
        email_address: str
            user email adress
        db_type: str
            database type to search against
        species_list: list
            species list to download if database is "CUSTOM"
        """
        
        # TODO complete
        #for species in species_list:
        #    if not self.input_validator.valid_species(species):
        #        return False
        return True

    def clean_internal_state(self):
        """clean job state dictionary

        Parameters
        ----------

        Returns
        -------
        """
        self.__j_manager.clean_internal_state()
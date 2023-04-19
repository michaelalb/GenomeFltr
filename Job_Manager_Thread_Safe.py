import datetime
import os
import pickle
from threading import Lock
from apscheduler.schedulers.background import BackgroundScheduler
from JobListener import PbsListener
import SharedConsts as sc
from SharedConsts import State
from utils import logger, LOGGER_LEVEL_JOB_MANAGE_THREAD_SAFE
from Monitor import Monitor_Jobs
import hashlib
import time
from math import floor
import shutil
logger.setLevel(LOGGER_LEVEL_JOB_MANAGE_THREAD_SAFE)


class Job_Manager_Thread_Safe:
    """
    This class manages and orchestrates all parts of the webserver i.e. the backend.
    The main flow of this architecture is based on an object we call a process (loosely releated to the actual meaning
     of the work process in the operating system).
    Each time a user starts a session in the front end ,in the Kraken webserver example this means uploading a file,
    and triggering the analysis of it, a unique process id is created and assigned to that session.
    Each process (mapped to a specific frontend session) can have multiple stages in its lifecycle,
     in the kraken example this can be pre-processing the file and running the Kraken search algorithm on it,
     or post processing the Kraken results.
    These lifecycle stages we call Jobs - the reason being is that this webserver backend stands on top of the PBS
    job management system. Meaning that each time you want to do something, it either has to be on the headnode
    (it is both bad practice and dangerous to preform heavy operations on the head node) or to be submitted as a job
    to the PBS system.
    These life cycle stages(Jobs) are mapped to a jobs state.
    These lifecycles(Jobs) are managed also by a components called the JobListener. This components samples the PBS
    system periodically and updates the job manager on the status of the respective jobs. The communication between
    these components is crucial.

    This manager is based on a dictionary that contains the processes data for all processes running on the webserver
    : __processes_state_dict
    The keys are process_id's and the values are their respective job_state (defined below)
    This class is designed to be generic and supports any number of different webservers!
    This is achieved by making this a base class for each webservers own manager. This manager is completely agnostic to
    what the process's lifecycles stages are, it simply makes sure they all happen in sequence.
    This is why this class alone, without implementing your own webservers job_manager is useless.

    THREAD SAFE OBJECT:
    As different threads are used in webservers, this is a thread safe object.
    When changing or reading data from __processes_state_dict it always with a mutex.

    ...

    Attributes
    ----------


    Methods
    -------
    implemented below
    """

    def __init__(self, max_number_of_process: int, upload_root_path: str, function2call_processes_changes_state: dict,
                 function2append_process: dict, paths2verify_process_ends: dict):
        """
        Creates the Job_Manager_Thread_Safe instances.
        The three dicts:
            1. function2call_processes_changes_state
            2. function2append_process
            3. paths2verify_process_ends
        Should have the same keys. The code will crash if not as a defense mechanize (the asserts below)

        Parameters
        ----------
        max_number_of_process : int
            Max number of process that can run simultaneously
        upload_root_path: str
            A path to where the folder of the process are.
        function2call_processes_changes_state: dict
            A dict of functions where the key is the job prefix and the value is the function to call when the job is updated.
        function2append_process: dict
            A dict of functions where the key is the job prefix and the value is the function to call when a new job is added.
        paths2verify_process_ends: dict
            A dict of functions where the key is the job prefix and the value is the function to call to verify the job is finished.

        Returns
        -------
        Job_Manager_Thread_Safe: Job_Manager_Thread_Safe
            instance of Job_Manager_Thread_Safe
        """
        self.__max_number_of_process = max_number_of_process
        self.__upload_root_path = upload_root_path
        self.__mutex_processes_state_dict = Lock()
        self.__mutex_processes_waiting_queue = Lock()
        assert len(function2call_processes_changes_state) == len(function2append_process) == len(
            paths2verify_process_ends), f'verify function2call_processes_changes_state, function2append_process and paths2verify_process_ends have all the required job_prefixes. Their len should be the same'
        assert function2call_processes_changes_state.keys() == function2append_process.keys() == paths2verify_process_ends.keys(), f'verify function2call_processes_changes_state, function2append_process and paths2verify_process_ends have the same keys. It should contain the job_prefixes'
        self.jobs_prefixes_lst = list(function2call_processes_changes_state.keys())
        self.__function2append_process = function2append_process
        self.__paths2verify_process_ends = paths2verify_process_ends
        function_to_call_listener = {}
        self.__processes_state_dict, self.__waiting_list = self.__read_processes_state_dict2file_and_waiting_list()
        self.__clean_processes_state_dict()
        for job_prefix in function2call_processes_changes_state.keys():
            function_to_call_listener[job_prefix] = self.__make_function_dict4listener(
                lambda process_id, state, _job_prefix=job_prefix: self.__set_process_state(process_id, state,
                                                                                           _job_prefix,
                                                                                           function2call_processes_changes_state[
                                                                                               _job_prefix]))
        # create listener on queue
        self.__listener = PbsListener(function_to_call_listener)
        self.__scheduler = BackgroundScheduler()
        self.__scheduler.add_job(self.__listener.run, 'interval', seconds=sc.INTERVAL_BETWEEN_LISTENER_SAMPLES)
        self.__scheduler.add_job(self.__clean_processes_state_dict, 'interval',
                                 minutes=sc.INTERVAL_BETWEEN_CLEANING_THE_PROCESSES_DICT * 60)
        self.__scheduler.start()
        self.__monitor = Monitor_Jobs(upload_root_path)

    def __save_processes_state_dict2file_and_waiting_list(self):
        """
        Saves the process dictionary and waiting list to file in order to restore it between shutdowns of the server.


        Parameters
        ----------

        Returns
        -------
        """
        file_to_store_dict = open(sc.PATH2SAVE_PROCESS_DICT, "wb")
        pickle.dump(self.__processes_state_dict, file_to_store_dict)
        file_to_store_dict.close()
        file_to_store_waiting_list = open(sc.PATH2SAVE_WAITING_LIST, "wb")
        pickle.dump(self.__waiting_list, file_to_store_waiting_list)
        file_to_store_waiting_list.close()

    def __read_processes_state_dict2file_and_waiting_list(self):
        """
        Reads the process dictionary from file in the __init__

        Parameters
        ----------

        Returns
        -------
        dict2return: dict
            the dictionary with the current processes and states
        """
        dict2return = {}
        if os.path.isfile(sc.PATH2SAVE_PROCESS_DICT):
            file_to_read = open(sc.PATH2SAVE_PROCESS_DICT, "rb")
            dict2return = pickle.load(file_to_read)
            file_to_read.close()
        for folder_name in os.listdir(self.__upload_root_path):
            if os.path.isdir(os.path.join(self.__upload_root_path, folder_name)):
                if not folder_name in dict2return:
                    dict2return[folder_name] = Job_State(os.path.join(self.__upload_root_path, folder_name), self.__function2append_process.keys(), '', '')
        
        logger.info(f'dict2return = {dict2return}')
        waiting_list2return = []
        if os.path.isfile(sc.PATH2SAVE_WAITING_LIST):
            file_to_read = open(sc.PATH2SAVE_WAITING_LIST, "rb")
            waiting_list2return = pickle.load(file_to_read)
            file_to_read.close()
        logger.info(f'waiting_list2return = {waiting_list2return}')
        return dict2return, waiting_list2return

    def __calc_days_since_modification_of_folder(self, folder_path):
        time_diff = time.time() - os.stat(folder_path).st_mtime
        return floor(time_diff / 60 / 60 / 24)

    def __clean_processes_state_dict(self):
        """
        Verifies the processes states are up to date.
        if the process is not up to date - it is removed from the process dictionary
        Three verifications are tested:
            1. a folder of the process exists ( this folder is used to contain all process related data)
            2. the date of the process haven't passed a expiration threshold - controlled by a const
            3. the time since the last modification to the folder is under a certain time - controlled by a const
        This function runs every certain time (by the BackgroundScheduler)

        Parameters
        ----------

        Returns
        -------
        """
        # important not to delete the elements of the dictionary while iterating over it
        # so we load it to a different list
        list_of_processes_to_verify = list(self.__processes_state_dict)
        for process_id in list_of_processes_to_verify:
            folder_path = os.path.join(self.__upload_root_path, process_id)
            time_process_started = self.__processes_state_dict[process_id].get_time_added()
            now = datetime.datetime.now()
            time_diff = now - time_process_started
            if not os.path.isdir(folder_path):
                del self.__processes_state_dict[process_id]
            elif time_diff.days >= sc.TIME_TO_SAVE_PROCESSES_IN_THE_PROCESSES_DICT:
                del self.__processes_state_dict[process_id]
                shutil.rmtree(folder_path) # delete folder
            elif self.__calc_days_since_modification_of_folder(folder_path) > sc.TIME_TO_KEEP_PROCSES_IDS_FOLDERS:
                del self.__processes_state_dict[process_id]
                shutil.rmtree(folder_path) # delete folder

    def __calc_num_running_processes(self):
        """
        Calculates the number of processes that running now.
        A process is running if one of it's job_prefixes is in State.Running, State.Queue, State.Init.

        Parameters
        ----------

        Returns
        -------
        running_processes: int
            number of running processes
        """
        running_processes = 0
        self.__mutex_processes_state_dict.acquire()
        for process_id in self.__processes_state_dict:
            for job_prefix in self.jobs_prefixes_lst:
                if self.__processes_state_dict[process_id].get_job_state(job_prefix) in [State.Running, State.Queue,
                                                                                         State.Init]:
                    running_processes += 1
                    break
        self.__mutex_processes_state_dict.release()
        return running_processes

    def __calc_process_id(self, pbs_id):
        """
        Calculates the mapping between the internal process ID and the current pbs_id of its running job (state).
       This is needed as the listener on the queue knows only the pbs_ids of the jobs (and thus need to be translated to process_id)

        Parameters
        ----------
        pbs_id: str
            the pbs_id of the process

        Returns
        -------
        process_id: str
            the process_id of this pbs_id, if not found, returns None
        """
        clean_pbs_id = pbs_id.split('.')[0]
        process_id2return = None
        self.__mutex_processes_state_dict.acquire()
        for process_id in self.__processes_state_dict:
            for job_prefix in self.jobs_prefixes_lst:
                if clean_pbs_id == self.__processes_state_dict[process_id].get_pbs_id(job_prefix):
                    process_id2return = process_id
                    break
        self.__mutex_processes_state_dict.release()
        if not process_id2return:
            logger.warning(f'clean_pbs_id = {clean_pbs_id} not in __processes_state_dict')
        return process_id2return

    def __log_and_set_change(self, pbs_id, set_process_state_func, state):
        """
        Updates the state of processes based on the calls from the listener

        Parameters
        ----------
        pbs_id: str
            the pbs_id of the process that the state need to be updated
        set_process_state_func: function
            the function to call for the update
        state: State (Enum)
            the new state of the job

        Returns
        -------
        """
        process_id = self.__calc_process_id(pbs_id)
        if state != State.Running:
            logger.info(f'pbs_id = {pbs_id}  process_id = {process_id} state is {state}')
        set_process_state_func(process_id, state)

    def __make_function_dict4listener(self, set_process_state):
        """
        As each of the processes types need to have different calling functions, here we create this mapping.
        This dictionary is then passed to the listener which based on the job prefix,
        and the state of the job calls the required function in the dictionary.
        
        There are 5 states for each job: Running, Long Running, Queue, Finished, and Crashed.
        This function creates a dict with the 5 function to call when each state is updated.
        The dict keys are the const of the States and the values are the function to call.
        Important! Each job type create a different dictionary (this happens in the __init__ of the class)

        Parameters
        ----------
        set_process_state_func: function
            the function to call for the update (this calls the function given in the __init__ which eventually calls the front and the UI)

        Returns
        -------
        dict: dict
            dictionary of function where the keys are the state and the values are the functions to call
        """
        return {
            sc.LONG_RUNNING_JOBS_NAME: lambda x: self.__log_and_set_change(x, set_process_state, State.Running),
            # TODO handle -currently same behevior as running
            sc.NEW_RUNNING_JOBS_NAME: lambda x: self.__log_and_set_change(x, set_process_state, State.Running),
            sc.QUEUE_JOBS_NAME: lambda x: self.__log_and_set_change(x, set_process_state, State.Queue),
            sc.FINISHED_JOBS_NAME: lambda x: self.__log_and_set_change(x, set_process_state, State.Finished),
            sc.ERROR_JOBS_NAME: lambda x: self.__log_and_set_change(x, set_process_state, State.Crashed),
        }

    def __set_process_state(self, process_id, state, job_prefix, func2update):
        """
        # todo: by this point i'm a bit lost - maybe with the design paper this will be better understood
        The function to change the state of the job in the processes dictionary.
        Locked with mutexes.
        If the state is finished or crashed, another process is added from the waiting list

        Parameters
        ----------
        process_id: str
            the ID of the process
        state: State (Enum)
            the state to change to
        job_prefix: str
            to which of the jobs the state should change
        func2update:
            the function to call once the updated completed

        Returns
        -------
        """
        if state != State.Running:
            logger.info(f'process_id = {process_id}, job_prefix = {job_prefix} state = {state}')
        email_address = None
        job_name = None

        # verify if the process is Finished or Crashed as they have similar behevior
        # uses the funciton from the __paths2verify_process_ends to distinguish between the beheviors
        if (state == State.Finished or state == State.Crashed) and process_id in self.__processes_state_dict:
            is_one_finished = None
            for func2create_file2check in self.__paths2verify_process_ends[job_prefix]:
                file2check = func2create_file2check(process_id)
                if file2check != '':  # if file2check is '' don't change the state
                    if os.path.isfile(file2check):
                        is_one_finished = True
                        break # state is finished
                    else:
                        is_one_finished = False
            if is_one_finished != None:
                if is_one_finished:
                    state = State.Finished
                else:
                    state = State.Crashed

        self.__mutex_processes_state_dict.acquire()
        if process_id in self.__processes_state_dict:
            self.__processes_state_dict[process_id].set_job_state(state, job_prefix)
            email_address = self.__processes_state_dict[process_id].get_email_address()
            job_name = self.__processes_state_dict[process_id].get_job_name()
        else:
            # TODO handle
            logger.warning(f'process_id {process_id} not in __processes_state_dict: {self.__processes_state_dict}')
        try:
            # update file with current process_state_dict
            self.__save_processes_state_dict2file_and_waiting_list()
        finally:
            self.__mutex_processes_state_dict.release()

        # adds process from the waiting list
        # don't put inside the mutex area - the funciton acquire the mutex too
        if state == State.Finished or state == State.Crashed:
            self.__add_process_from_waiting_list()
        
        try:
            # monitor the processes states
            self.__monitor.update_monitor_data(process_id, state, job_prefix, {})
        except Exception as e:
            logger.error(e)

        func2update(process_id, state, email_address, job_name, job_prefix)

    def __add_process_from_waiting_list(self):
        """
        If the number of running processes is equal to the max_number_of_process (given in the __init__), 
        then new added processes are added to the waiting list (this means that the jobs are **NOT** submitted 
        to the PBS system and queued there but waits inside the backend).
        Thus, when a process is finished, the backend needs to submit the process from the waiting list (which will be implemented here)
        
        Adds a process from the waiting list.
        Gets the first process in the waiting list, and submit it with the it's parameters

        Parameters
        ----------

        Returns
        -------
        """
        # first value if the process_id to add
        # second value is the job_type of
        # third value is the parameters of the job (this is a dict as we don't know how many parameters are used)
        process2add, job_type, running_arguments = self.__pop_from_waiting_queue()
        if process2add:
            logger.debug(
                f'adding new process after processed finished process2add = {process2add} job_type = {job_type}')
            # running parameters are dictionary and thus the amount of parameters can be different from different processes
            self.add_process(process2add, job_type, *running_arguments)

    def add_process(self, process_id: str, job_prefix, *args):
        """
        Adds a process to the queue. Calls the function to add the process and saves the returned pbs_id to the processes dictionary.
        The front (and the UI) find the required parameters for the job (by the user choices) and calls this function.
        This function actually triggers the creation of the job itself (and thus will submit the job to the PBS system).
        
        As different jobs have different number of parameters, we use args.
        If the number of processes is higher than the number allowed, the process is added to the waiting list

        Parameters
        ----------
        process_id: str
            the ID of the process
        job_prefix: str
            the type of the process to add
        args:
            the arguments the process needs

        Returns
        -------
        """
        logger.info(f'process_id = {process_id}, job_prefix = {job_prefix}, args = {args}')
        # don't put inside the mutex area - the funciton acquire the mutex too
        running_processes = self.__calc_num_running_processes()
        self.__mutex_processes_state_dict.acquire()
        if running_processes < self.__max_number_of_process:
            process_folder_path = os.path.join(self.__upload_root_path, process_id)
            if process_id not in self.__processes_state_dict:
                email_address = args[0]
                job_name = args[1]
                self.__processes_state_dict[process_id] = Job_State(process_folder_path,
                                                                    self.__function2append_process.keys(),
                                                                    email_address,
                                                                    job_name)

            try:
                pbs_id = self.__function2append_process[job_prefix](process_folder_path, *args)
                logger.debug(
                    f'process_id = {process_id} job_prefix = {job_prefix} pbs_id = {pbs_id}, process has started')
                self.__processes_state_dict[process_id].set_job_state(State.Init, job_prefix)
                self.__processes_state_dict[process_id].set_pbs_id(pbs_id, job_prefix)
                # hash the email address so it won't be saved in the montired files
                args = list(args)
                args[0] = hashlib.sha256(args[0].encode('utf-8')).hexdigest()
                self.__monitor.update_monitor_data(process_id, State.Init, job_prefix, {'input_parameters': args})
            except Exception as e:
                logger.error(e)

        else:
            self.__mutex_processes_waiting_queue.acquire()
            logger.info(f'process_id = {process_id} job_prefix = {job_prefix}, adding to waiting list')
            self.__waiting_list.append((process_id, job_prefix, args))
            self.__mutex_processes_waiting_queue.release()

        try:
            # update file with current process_state_dict
            self.__save_processes_state_dict2file_and_waiting_list()
        finally:
            self.__mutex_processes_state_dict.release()

    def __pop_from_waiting_queue(self):
        """
        This function is used by __add_process_from_waiting_list to pop process from the waiting list.
        Locked with mutexes to make sure no race conditions occur.
        If no process is in the waiting queue then the returned value is None

        Parameters
        ----------

        Returns
        -------
        """
        self.__mutex_processes_waiting_queue.acquire()
        process_tuple2return = None, None, None
        if len(self.__waiting_list) > 0:
            process_tuple2return = self.__waiting_list.pop(0)
        self.__mutex_processes_waiting_queue.release()
        logger.info(f'process2return = {process_tuple2return}')
        return process_tuple2return

    def get_job_state(self, process_id: str, job_prefix: str):
        """
        Returns the job state of a given process by process Id.
        locked with mutexes.

        Parameters
        ----------
        process_id: str
            the ID of the process
        job_prefix: str
            the job type

        Returns
        -------
        state: State (Enum)
            the current state of this job
        """
        state2return = None
        self.__mutex_processes_state_dict.acquire()
        if process_id in self.__processes_state_dict:
            state2return = self.__processes_state_dict[process_id].get_job_state(job_prefix)
        # important to keep as if and NOT elif or else
        # for PostProcess the returned value is None even when it is in the dict
        if state2return == None:
            self.__mutex_processes_waiting_queue.acquire()
            for process_tuple in self.__waiting_list:
                if process_id in process_tuple:
                    state2return = State.Waiting
                    break
            self.__mutex_processes_waiting_queue.release()
        self.__mutex_processes_state_dict.release()
        #logger.info(f'state2return = {state2return} job_prefix = {job_prefix}')
        return state2return

    def get_job_name(self, process_id: str):
        """
        Returns the job name of a given process by process Id.

        Parameters
        ----------
        process_id: str
            the ID of the process

        Returns
        -------
        job_name: str 
            The job name (optional) inserted by the user. If none is inserted then job_name = ""
        """
        if process_id in self.__processes_state_dict:
            return self.__processes_state_dict[process_id].get_job_name()
        return None

    def clean_internal_state(self):
        """
        cleans the internal state of the sever:
            1. override the waiting queue
            2. override the processes dictionary.
        Then saves the empty dictionary to the file (so it cleans the saved file too)

        Parameters
        ----------

        Returns
        -------
        """
        self.__mutex_processes_state_dict.acquire()
        self.__mutex_processes_waiting_queue.acquire()

        self.__processes_state_dict = {}
        self.__waiting_list = []

        self.__mutex_processes_waiting_queue.release()
        try:
            # update file with current process_state_dict
            self.__save_processes_state_dict2file_and_waiting_list()
        finally:
            self.__mutex_processes_state_dict.release()


class Job_State:
    """
    A class to contain the lifecycle(state) information about a process.
    Remember! some processes can have number of jobs.
    For example, when a user upload a file, first the Kraken search job is created.
    Then (after user analysis), another job is added - the post process.
    As both jobs are on the same session - they will both have the same process_id.
    As the backend doesn't know about the jobs themselves, everything is matched by the job_prefixes that are inserted from __init__.

    ...

    Attributes
    ----------
    

    Methods
    -------
    implemented below
    """
    def __init__(self, folder_path: str, jobs_prefixes_lst: list, email_address, job_name):
        """
        Creates the Job_State instances.
        Check comments above for more information

        Parameters
        ----------
        folder_path : str
            Max number of process that can run simultaneously
        jobs_prefixes_lst: list
            A path to the saved files. Each process in there creates it's own folder
        email_address: str
            email adress
        job_name: str
            The job name (optional) inserted by the user. If none is inserted then job_name = ""

        Returns
        -------
        job_state: Job_State
            instance of Job_State
        """
        self.__folder_path = folder_path
        # init a dictionary with all of the possilbe job prefixes and None as at init none of the jobs has been started
        self.__job_states_dict = {prefix: None for prefix in jobs_prefixes_lst}
        self.__time_added = datetime.datetime.now()
        # contians the pbs_ids for all possible jobs. Different jobs will have different pbs_ids
        self.__pbs_id_dict = {prefix: None for prefix in jobs_prefixes_lst}
        self.__email_address = email_address
        self.__job_name = job_name

    def set_job_state(self, new_state: State, job_prefix: str):
        """set the new job state
        
        Parameters
        ----------
        new_state : State (Enum)
            The new state to update
        job_prefix: str
            The job that the new state correspond too

        Returns
        -------
        """
        if job_prefix in self.__job_states_dict:
            self.__job_states_dict[job_prefix] = new_state
        else:
            logger.error(f'job_prefix = {job_prefix} not in self.__job_states_dict = {self.__job_states_dict}')
        
    def get_job_state(self, job_prefix: str):
        """get job state
        
        Parameters
        ----------
        job_prefix: str
            The job that the state correspond too

        Returns
        -------
        state: State (Enum)
            The state of this job prefix
        """
        if job_prefix in self.__job_states_dict:
            return self.__job_states_dict[job_prefix]
        else:
            logger.error(f'job_prefix = {job_prefix} not in self.__job_states_dict = {self.__job_states_dict}')
        
    def set_pbs_id(self, pbs_id: str, job_prefix: str):
        """set the new pbs id
        
        Parameters
        ----------
        pbs_id: str
            The pbs_id
        job_prefix: str
            The job that the new state correspond too

        Returns
        -------
        """
        if job_prefix in self.__job_states_dict:
            self.__pbs_id_dict[job_prefix] = pbs_id
        else:
            logger.error(f'job_prefix = {job_prefix} not in self.__pbs_id_dict = {self.__pbs_id_dict}')
        
    def get_pbs_id(self, job_prefix: str):
        """get the pbs id
        
        Parameters
        ----------
        job_prefix: str
            The job that the pbs correspond too

        Returns
        -------
        pbs_id: str
            The job pbs of this job prefix
        """
        if job_prefix in self.__pbs_id_dict:
            return self.__pbs_id_dict[job_prefix]
        else:
            logger.error(f'job_prefix = {job_prefix} not in self.__pbs_id_dict = {self.__pbs_id_dict}')
        
    def get_email_address(self):
        """get the email address
        
        Parameters
        ----------

        Returns
        -------
        email_address: str
            the email adress of the user
        """
        return self.__email_address
        
    def get_time_added(self):
        """get the time the process have been added
        
        Parameters
        ----------

        Returns
        -------
        time_added: time
            the time the process have been added
        """
        return self.__time_added
        
    def get_job_name(self):
        """get the job name
        
        Parameters
        ----------

        Returns
        -------
        job_name: str
            The job name (optional) inserted by the user. If none is inserted then job_name = ""
        """
        return self.__job_name
        
    def __str__(self):
        """a string represenation of the object
        print(Job_State)
        Parameters
        ----------

        Returns
        -------
        represenation: str
            how the object will be looked when using print(Job_State)
        """
        obj_string = ''
        obj_string += 'job_states_dict: ' + str(self.__job_states_dict)
        obj_string += 'time_added: ' + str(self.__time_added)
        obj_string += 'email_address: ' + str(self.__email_address)
        obj_string += 'job_name: ' + str(self.__job_name)
        return obj_string

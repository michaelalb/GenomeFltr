from SharedConsts import State, PATH2SAVE_MONITOR_DATA, SEPERATOR_FOR_MONITOR_DF, KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME
import os
from utils import logger
from datetime import datetime
import glob
import json


class Monitor_Jobs:
    """
    This class manages and orchestrates all parts of monitoring the usage of the webserver.
    Job_Manager_Thread_Safe.py calls this class when the states of the processes changes, and this class saves the process new state into files.
    ...

    Attributes
    ----------


    Methods
    -------
    implemented below
    """

    def __init__(self, upload_root_path):
        """
        The function makes sure the folder to save object exists.
        This although creates the __customs_functions which will generate the data per process per state (only customs). If no need for custom data, leave it empty.
        Before you start changing the custom function! look at the data saved every state update (the general data).
        The way to add functinos is very important: the name of the function should be: {job_prefix}_{state}. For example, if you want to add sepcific data for the State.Finished for the KR process, the name of the function (the key of the dict) will be: KR_Finished. The value of this will be the functions that returns the dict with specific data.
        
        
        **Usually developers should change only the self.__customs_fucntions.
        Parameters
        ----------
        upload_root_path: str
            A path to where the folder of the process are.
            
        Returns
        -------
        Monitor_Jobs: Monitor_Jobs
            instance of Monitor_Jobs
        """
        self.COLUMNS_TITLES = ['state', 'time', 'job_prefix', 'path_to_folder', 'parameters']
        self.__upload_root_path = upload_root_path
        
        if not os.path.exists(PATH2SAVE_MONITOR_DATA):
            os.makedirs(PATH2SAVE_MONITOR_DATA)
            
        try:
            """
            functions declared shoule have the following:
                1. key of the function: {job_prefix}_{state} # check example above
                2. process_id is the only parameter of these functions (you can calc the folder of the process via os.path.join(self.__upload_root_path, process_id))
                3. returns a dictionary with the results for further analysis
            """
            def KR_Init(process_id):
                paraemeters = {}
                parent_folder = os.path.join(self.__upload_root_path, process_id)
                for file in glob.glob(parent_folder + "/*"):
                    file_name = os.path.basename(file)
                    paraemeters[f'{file_name}_size'] = os.stat(file).st_size
                return paraemeters
                
            def KR_Finished(process_id):
                paraemeters = {}
                parent_folder = os.path.join(self.__upload_root_path, process_id)
                summary_path = os.path.join(parent_folder, KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME)
                if os.path.isfile(summary_path):
                    with open(summary_path) as summary_file:
                        paraemeters = json.load(summary_file)
                return paraemeters
                
            self.__customs_fucntions = {
                'KR_Init': KR_Init,
                'KR_Finished': KR_Finished
            }
        except Exception as e:
            logger.error(e)
            self.__customs_fucntions = {}
        
    def calc_general_data(self, process_id, state, job_prefix):
        """
        This function is for every change of process state.
        This calculates the general stuff important for all of the different states and jobs types.
        If a data is required for only a specific state, please use the self.__customs_fucntions (see above).
        
        **The data retured should be in the same order as the self.COLUMNS_TITLES!!
        
        Parameters
        ----------
        state: State (Enum)
            the new state of the job
        job_prefix: str
            to which of the jobs the state should change
        process_id: str
            the ID of the process
        
        Returns
        -------
        general_data: list
            a list with the general data
        """
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        path2process_folder = os.path.join(self.__upload_root_path, process_id)
        return [state.name, now_str, job_prefix, path2process_folder]
        
    def update_monitor_data(self, process_id, state, job_prefix, parameters):
        """
        This function is called when the state of the jobs updates.
        This function writes the data into the correct file at: PATH2SAVE_MONITOR_DATA/{process_id}.csv
        The data written to those files contains two parts:
            1. General - this include: time of update, the new state, job_prefix, path_to_folder
            2. Custom per state - for example, in this webserver we are intreseted in the summary text when the job is finished. Thus this data will be added only when the KR process is finished.
        
        Parameters
        ----------
        state: State (Enum)
            the new state of the job
        job_prefix: str
            to which of the jobs the state should change
        process_id: str
            the ID of the process
        parameters: dict
            parameters to add to custom_data
        
        Returns
        -------
        """
        
        path2monitor_data = f'{os.path.join(PATH2SAVE_MONITOR_DATA, process_id)}.csv'
        #creates the file if not exists and add the tiltes columns
        if not os.path.isfile(path2monitor_data):
            with open(path2monitor_data, 'w') as monitor_file:
                monitor_file.write(SEPERATOR_FOR_MONITOR_DF.join(self.COLUMNS_TITLES) + '\n')
                
        # calculate the general data
        data = self.calc_general_data(process_id, state, job_prefix)
        custom_func_key = f'{job_prefix}_{state.name}'
        
        # adds the custom data
        if self.__customs_fucntions.get(custom_func_key) != None:
            try:
                custom_dict = self.__customs_fucntions.get(custom_func_key)(process_id)
                custom_dict.update(parameters)
                data.append(str(custom_dict))
            except Exception as e:
                logger.error(e)
        else:
            # no custom data is needed
            data.append(str(parameters))
            
        with open(path2monitor_data, 'a') as monitor_file:
            monitor_file.write(SEPERATOR_FOR_MONITOR_DF.join(data) + '\n')
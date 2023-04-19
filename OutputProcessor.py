import argparse
import operator
from itertools import groupby
from operator import itemgetter
from pathlib import Path
import os
import pandas as pd
from SharedConsts import K_MER_COUNTER_MATRIX_FILE_NAME, RESULTS_FOR_OUTPUT_CLASSIFIED_RAW_FILE_NAME, \
    DF_LOADER_CHUCK_SIZE, RESULTS_COLUMNS_TO_KEEP, RESULTS_FOR_OUTPUT_UNCLASSIFIED_RAW_FILE_NAME, \
    UNCLASSIFIED_COLUMN_NAME, RESULTS_SUMMARY_FILE_NAME, SUMMARY_RESULTS_COLUMN_NAMES, TEMP_CLASSIFIED_IDS, \
    TEMP_UNCLASSIFIED_IDS, KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME, KRAKEN_UNCLASSIFIED_COLUMN_NAME, \
    RANK_KRAKEN_TRANSLATIONS, UNCLASSIFIED_BACTERIA_NAME, UNCLASSIFIED_BACTERIA_ID
import json
import re
import numpy as np


def parse_kmer_data(kraken_raw_output_df, is_paired=False):
    """
    parses the k mer column in the kraken output into a list of pairs (species of k-mer, number of matched k-mers)
    :param kraken_raw_output_df:  data frame of the kraken output
    :param is_paired:  indicator whether the data comes from paired results or not
    :return: the same df with the "split" column parsed
    """
    # split list and makes pairs (specie, k-mers)
    kraken_raw_output_df['split'] = kraken_raw_output_df['all_classified_K_mers'].apply(
        lambda x: [y.split(':') for y in x.split()])
    # sort by specie (inside each row)
    kraken_raw_output_df['split'] = kraken_raw_output_df['split'].apply(lambda x: sorted(x, key=itemgetter(0)))
    # group by specie and count by k-mers
    kraken_raw_output_df['split'] = kraken_raw_output_df['split'].apply(lambda x: [(key, sum(
        [int(y[1]) for y in group])) for key, group in groupby(x, key=itemgetter(0))])

    if is_paired:
        # repeat the process for the second read
        # split list and makes pairs (specie, k-mers)
        kraken_raw_output_df['split_2'] = kraken_raw_output_df['all_classified_K_mers_2'].apply(
            lambda x: [y.split(':') for y in x.split()])
        # sort by specie (inside each row)
        kraken_raw_output_df['split_2'] = kraken_raw_output_df['split_2'].apply(lambda x: sorted(x, key=itemgetter(0)))
        # group by specie and count by k-mers
        kraken_raw_output_df['split_2'] = kraken_raw_output_df['split_2'].apply(lambda x: [(key, sum(
            [int(y[1]) for y in group])) for key, group in groupby(x, key=itemgetter(0))])

        # combine them
        kraken_raw_output_df['split_comb'] = kraken_raw_output_df['split'] + kraken_raw_output_df['split_2']
        # sort by specie (inside each row)
        kraken_raw_output_df['split_comb'] = kraken_raw_output_df['split_comb'].apply(lambda x: sorted(x, key=itemgetter(0)))
        # group by specie and count by k-mers - max
        kraken_raw_output_df['split'] = kraken_raw_output_df['split_comb'].apply(lambda x: [(key, max(
            [int(y[1]) for y in group])) for key, group in groupby(x, key=itemgetter(0))])

        kraken_raw_output_df.drop(columns=['split_comb', 'split_2'], inplace=True)

    return kraken_raw_output_df


def get_NCBI_renaming_dict(summary_res_df):
    """
    extracts the ncbi taxonomy data from the karaken summary file
    :param summary_res_path: path to the relevant kraken
    :return:
    """
    temp_naming_df = summary_res_df[['ncbi_taxonomyID', 'name']]
    temp_naming_df['ncbi_taxonomyID'] = temp_naming_df['ncbi_taxonomyID'].astype(str)
    temp_naming_df['name'] = temp_naming_df['name'] + ' (taxid ' + temp_naming_df['ncbi_taxonomyID'] + ')'
    renaming_dict = temp_naming_df.set_index('ncbi_taxonomyID').to_dict()['name']
    # add unclassified bacteria
    assert UNCLASSIFIED_BACTERIA_ID not in renaming_dict.keys()
    renaming_dict[UNCLASSIFIED_BACTERIA_ID] = UNCLASSIFIED_BACTERIA_NAME
    renaming_dict['A'] = 'Low quality reads'
    return renaming_dict


def calc_kmer_statistics(kmer_df):
    """
    this function calculates the k-mer metrics needed for the output matrix
    :param kmer_df: the mid processing k-mer data frame
    :return: kmer_df with a few more k-mer statistics columns
    """
    # fix reads that have only high level k-mers matches like "Bacteria"
    kmer_df['split'] = kmer_df['split'].apply(lambda x: x if len(x) > 0 else [(UNCLASSIFIED_BACTERIA_ID, 1)])
    # calculate sum of k mers
    kmer_df['total_k_mer_count'] = kmer_df['split'].apply(lambda x: sum([i[1] for i in x]))
    # remove unclassified classification
    kmer_df['split'] = kmer_df['split'].apply(lambda x: [a for a in x if a[0] != '0'])
    # kmer_df['split'] = kmer_df['split'].apply(lambda x: [a for a in x if a[0] != 'A'])
    kmer_df.loc[kmer_df['is_classified'] == 'U', 'split'] = kmer_df.loc[kmer_df['is_classified'] == 'U', :].apply(lambda x: [('0', x['total_k_mer_count'])], axis=1)
    kmer_df['is_empty'] = kmer_df['split'].astype(bool)
    kmer_df.loc[kmer_df['is_empty'] == False, 'split'] = kmer_df.loc[kmer_df['is_empty'] == False, :].apply(lambda x: [('-1', x['total_k_mer_count'])], axis=1)
    # calculate max species
    kmer_df['max_specie'] = kmer_df['split'].apply(lambda x: max(x, key=itemgetter(1))[0])
    # calculate k-mers
    kmer_df['max_k_mer_count'] =  kmer_df['split'].apply(lambda x: sum(map(operator.itemgetter(1), x)))
    # calculate percentile
    kmer_df['max_k_mer_p'] = kmer_df['max_k_mer_count'] / kmer_df['total_k_mer_count']
    # sort into bins according to the percentile of k-mers
    kmer_df["bins_max_k_mer_p"] = pd.cut(kmer_df["max_k_mer_p"], [x / 100 for x in range(101)], precision=0,
                                         labels=[x / 100 for x in range(1, 101)], right=True)

    return kmer_df


def process_output(**kwargs):
    """
    reads kraken results in manageable chunks and pre-processes the results for the UI and final output exports
    :param kwargs: must have a key "outputFilePath"
    :return: the number of unclassified organisms
    """
    # parse arguments and set up
    outputFilePath = Path(kwargs['outputFilePath'])
    remove_only_high_level_res = kwargs['remove_only_high_level_res']

    if outputFilePath is None:
        raise Exception("no output file path was provided for pre-processor")

    root_folder = outputFilePath.parent
    processed_for_UI_results_path = root_folder / K_MER_COUNTER_MATRIX_FILE_NAME
    processed_Unclassified_for_PostProcess_results_path = \
        root_folder / RESULTS_FOR_OUTPUT_UNCLASSIFIED_RAW_FILE_NAME
    processed_Classified_for_PostProcess_results_path = \
        root_folder / RESULTS_FOR_OUTPUT_CLASSIFIED_RAW_FILE_NAME
    results_summary_path = root_folder / RESULTS_SUMMARY_FILE_NAME
    temp_unclass_path = root_folder / TEMP_UNCLASSIFIED_IDS
    temp_class_path = root_folder / TEMP_CLASSIFIED_IDS
    kraken_summary_results_For_UI_path = root_folder / KRAKEN_SUMMARY_RESULTS_FOR_UI_FILE_NAME
    how_many_unclassified = 0
    # used later to prepare the files for faster post process
    classified_ids = []
    unclassified_ids = []

    # make sure there are no old things that will make the df appending wrong
    for file in [processed_Classified_for_PostProcess_results_path, processed_Unclassified_for_PostProcess_results_path,
                 processed_for_UI_results_path]:
        if file.is_file():
            os.remove(str(file))

    # prepare renaming dict
    summary_res_df = pd.read_csv(results_summary_path, sep='\t', names=SUMMARY_RESULTS_COLUMN_NAMES)
    summary_res_df['name'] = summary_res_df['name'].str.strip()
    summary_res_df['rank_code'] = summary_res_df['rank_code'].str.rstrip('1234567890')
    # fix high level k-mers
    high_level_k_mers = summary_res_df[summary_res_df['rank_code'].isin(['R', 'K', 'D', 'P'])]['ncbi_taxonomyID'].values
    if high_level_k_mers.size == 0:
        high_level_k_mers = np.array(['STAM'])  # dummy value to fix small results issue (when there is no contamination)
    regex_exp_for_high_class_orig = '[^0-9]' + '(' + '|'.join(high_level_k_mers.astype(str)) + ')' + ':[0-9]+'
    regex_exps = [regex_exp_for_high_class_orig]
    levels = ['high_level_removed']
    if not remove_only_high_level_res:  # in case we want to do this for each level
        levels += ['D', 'K', 'P', 'C', 'O', 'F', 'G', 'S']
        for level_of_classification in ['D', 'K', 'P', 'C', 'O', 'F', 'G', 'S']:
            level_k_mers = summary_res_df[~summary_res_df['rank_code'].isin([level_of_classification])]['ncbi_taxonomyID'].values
            if level_k_mers.size == 0:
                level_k_mers = np.array(['STAM'])  # dummy value to fix small results issue (when there is no contamination)
            regex_exp_for_high_class_temp = '[^0-9]' + '(' + '|'.join(level_k_mers.astype(str)) + ')' + ':[0-9]+'
            regex_exps.append(regex_exp_for_high_class_temp)

    ncbi_renaming_dict = get_NCBI_renaming_dict(summary_res_df)

    # create summary statistics json for UI
    if len(summary_res_df[summary_res_df['rank_code'] == 'U'].index) == 0:
        percent_of_contamination = 0
    else:
        percent_of_contamination = round(100 - summary_res_df[summary_res_df[
                                                                  'rank_code'] == 'U']['percentage_of_reads'].iloc[0], 2)
    summary_res_for_UI_df = summary_res_df[summary_res_df['rank_code'] == 'C'].sort_values('percentage_of_reads',
                                                                                             ascending=False)
    number_of_classes = len(summary_res_for_UI_df.index)
    most_common_class = summary_res_for_UI_df.head(1)['name'].iloc[0] if number_of_classes > 0 else 'No contamination Found'
    summary_res_for_UI_dict = {'percent_of_contamination': percent_of_contamination, 'most_common_class_contamination':
        most_common_class, 'number_of_classes': number_of_classes}
    with open(kraken_summary_results_For_UI_path, 'w') as jsp:
        json.dump(summary_res_for_UI_dict, jsp)

    # main processing loop
    for i, level in zip(range(len(regex_exps)), levels):
        regex_exp_for_high_class = regex_exps[i]
        first = True
        for chunk in pd.read_csv(outputFilePath, sep='\t', header=None, chunksize=DF_LOADER_CHUCK_SIZE):


            # process the results
            chunk.rename(columns={0: 'is_classified', 1: "read_name", 2: "classified_species", 3: "read_length",
                                  4: "all_classified_K_mers"}, inplace=True)

            # treat paired run format
            is_paired = chunk.iloc[0]['all_classified_K_mers'].find('|:|') != -1
            if is_paired:
                chunk['all_classified_K_mers'] = chunk['all_classified_K_mers'].str.split("\|:\|")
                chunk['all_classified_K_mers_2'] = chunk['all_classified_K_mers'].apply(lambda x: itemgetter(1)(x))
                chunk['all_classified_K_mers'] = chunk['all_classified_K_mers'].apply(lambda x: itemgetter(0)(x))
                # chunk['read_length'] = chunk['read_length'].str.split('\|').apply(lambda x: max(x))

            # remove high order k-mers - Note this has a bug for paired end if we want to put it back
            # it does not look at all_classified_K_mers_2
            # chunk['to_remove'] = ' '
            # chunk['all_classified_K_mers'] = chunk['to_remove'].str.cat(chunk['all_classified_K_mers'])
            # chunk.drop(columns='to_remove', inplace=True)
            # chunk['all_classified_K_mers'] = chunk['all_classified_K_mers'].str.replace(regex_exp_for_high_class, '')

            # calculations
            chunk = parse_kmer_data(chunk, is_paired)
            chunk = calc_kmer_statistics(chunk)
            # typing and naming
            chunk.replace({"max_specie": ncbi_renaming_dict}, inplace=True)
            # address max_species not found in renaming dict
            # convert them to Kraken results
            chunk['unmapped'] = chunk['max_specie'].str.isnumeric()
            chunk.loc[chunk['unmapped'] == True, 'max_specie'] = chunk.loc[chunk['unmapped'] == True, 'classified_species']
            # remove the high level ones
            chunk['taxid'] = '-1'
            chunk.loc[chunk['unmapped'] == True, 'taxid'] = chunk.loc[
                chunk['unmapped'] == True, 'max_specie'].str.replace("[^0-9]", "")
            chunk['taxid'] = chunk['taxid'].astype(int)
            chunk['unmapped_taxid'] = False
            chunk.loc[chunk['unmapped'] == True, 'unmapped_taxid'] = chunk.loc[chunk['unmapped'] == True, 'taxid'].isin(high_level_k_mers)
            chunk = chunk.loc[~chunk.unmapped_taxid, :]
            chunk.drop(columns=['unmapped', 'taxid', 'unmapped_taxid'], inplace=True)
            # back to flow
            chunk['max_k_mer_p'] = chunk['max_k_mer_p'].astype(float)
            chunk['all_classified_K_mers'] = chunk['all_classified_K_mers'].astype(str)
            chunk['classified_species'] = chunk['classified_species'].astype(str)

            # separate unclassified and classified results
            # fix kraken discrepancy with us
            kraken_mistakes = chunk[(chunk['is_classified'] == 'C') & (chunk['max_specie'] == KRAKEN_UNCLASSIFIED_COLUMN_NAME)]
            chunk.drop(kraken_mistakes.index, inplace=True)
            # actually separate
            unclassified_chunk = chunk[chunk['is_classified'] == 'U'].append(kraken_mistakes)
            classified_chunk = chunk[chunk['is_classified'] == 'C']
            how_many_unclassified += len(unclassified_chunk.index)

            # create UI results matrix where its percentiles as rows, k-mers as columns and counts as values
            df_preprocess_temp = pd.crosstab(classified_chunk.max_specie, classified_chunk.bins_max_k_mer_p).T

            # save results: ( we assume the first regex exp is the regular one - all high levels removed
            if i == 0:
                classified_ids += list(classified_chunk["read_name"])
                unclassified_ids += list(unclassified_chunk["read_name"])
            else:
                processed_Unclassified_for_PostProcess_results_path += RANK_KRAKEN_TRANSLATIONS.get(level, 'NameNotFound')
                processed_Classified_for_PostProcess_results_path += RANK_KRAKEN_TRANSLATIONS.get(level, 'NameNotFound')

            if first:
                unclassified_chunk[RESULTS_COLUMNS_TO_KEEP].to_csv(str(processed_Unclassified_for_PostProcess_results_path),
                                                                   mode='a', header=True, index=False)
                classified_chunk[RESULTS_COLUMNS_TO_KEEP].to_csv(str(processed_Classified_for_PostProcess_results_path),
                                                                 mode='a', header=True, index=False)
                df_preprocess = df_preprocess_temp
                first = False
            else:
                unclassified_chunk[RESULTS_COLUMNS_TO_KEEP].to_csv(str(processed_Unclassified_for_PostProcess_results_path),
                                                                   mode='a', header=False, index=False)
                classified_chunk[RESULTS_COLUMNS_TO_KEEP].to_csv(str(processed_Classified_for_PostProcess_results_path),
                                                                 mode='a', header=False, index=False)
                df_preprocess = df_preprocess.append(df_preprocess_temp)

        # save final matrix for UI
        df_preprocess.fillna(0, inplace=True)
        df_preprocess = df_preprocess.astype(int)
        df_preprocess = df_preprocess.groupby(df_preprocess.index).sum()
        # add unclassified to matrix
        df_preprocess[UNCLASSIFIED_COLUMN_NAME] = 0
        line = pd.DataFrame(data=[[0 for i in df_preprocess.columns]], columns=df_preprocess.columns, index=[0.00])
        line[UNCLASSIFIED_COLUMN_NAME] = how_many_unclassified
        df_preprocess = line.append(df_preprocess)

        df_preprocess.to_csv(processed_for_UI_results_path)

    # create search lists for SeqKit
    classified_ids_string = '\n'.join([str(k) for k in classified_ids])
    unclassified_ids_string = '\n'.join([str(k) for k in unclassified_ids])
    with open(temp_class_path, 'w') as fp:
        fp.write(classified_ids_string)
    with open(temp_unclass_path, 'w') as fp:
        fp.write(unclassified_ids_string)

    # make sure permissions are good
    processed_for_UI_results_path.chmod(777)
    processed_Classified_for_PostProcess_results_path.chmod(777)
    processed_Unclassified_for_PostProcess_results_path.chmod(777)

    return how_many_unclassified


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Running RL project Main')
    parser.add_argument('--outputFilePath', default=None, help='path to output file to process')
    parser.add_argument('--remove_only_high_level_res', default=True, help='path to output file to process')
    args = parser.parse_args()
    process_output(**vars(args))

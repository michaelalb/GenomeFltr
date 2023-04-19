const HELP_TEXT_INSERTING_MAIL = `
    Your email is required to inform you the analysis has finished.
    It will not be used for anything else.`
const HELP_TEXT_UPLOADING_FILE = `
    The reads file should be in fasta, fastq, or a gz compressed fasta. Paired reads should be uploaded in two separate files. The number of reads is limited to 50 million paired reads or 100 million single reads.`
const HELP_TEXT_CHOOSING_DATABASE = `
    Please select the database against which reads should be filtered.
    Please select 'custom' to provide your own selection of potential contaminating organisms.`
const HELP_TEXT_CUSTOM_DATABASE = `
    Please enter at least one valid TAXA ID with a RefSeq genome. We will build a filter based on the taxa you have entered.
    To download specific RefSeq genomes, press the 'setting' button on the bottom right corner. Then, for each TAXA ID you could insert up to three ACCESSION IDS to speicify genomes, which will be downloaded from the RefSeq database (RefSeq accessions start with three letter prefix "GCF"). MMake sure to enter the right ACCESSION IDS (if wrong ones are entered or nothing was specified, up to three genomes will be randomly downloaded). One could view the genomes that were used to filter the reads in the 'results' page.`
const HELP_TEXT_SUMMARY_PAGE = `
    Please verify the job parameters. Press the 'RESET' button if you want to change something.`

const HELP_TEXT_BAR_SIMILARITES = `
    The following histogram displays the similarity of the reads to the reference genomes. The x-axis is the percent of similarity. A value of '1' represents a perfect match and '0' no match. The y-axis is the number of reads.
    Move the mouse on the bars to see the values. To choose the k-mer threshold, simply click on the graph (reads with lower similarity than the k-mer threshold will not be filtered). No contaminated reads are in blue while orange indicates contaminated reads. The percentage of filtered reads is indicated in the pie chart on the right panel.`
const HELP_TEXT_SPECIES_LIST = `
    The following list displays the contaminant taxa present in your reads data. On the left side, the taxon names are displayed. On the right side, the number of reads that matched this taxon.
    If a checkbox is marked, the species will be filtered., otherwise it will be retained. To choose if the species is filtered or not simply click on the box next to it. The category “Low quality reads” indicates reads that contain ambiguities and that are not processed by the algorithm. We do not recommend to filter this category nor to filter reads that mapped to the root node (taxid 1) and to the node cellular organisms (taxid 131567).`
const HELP_TEXT_PIE_CHART = `
    The following piechart displays the frequency of retained and filtered reads based on the threshold indicated in the histogram on the left panel.`
const HELP_TEXT_CONFIRM_EXPORT_NO_CHANGE = `
    Are you sure? 
    You did not change any of the default filtering parameters. Click on the graph and checkboxes to choose different filtering thresholds and species to filter.`

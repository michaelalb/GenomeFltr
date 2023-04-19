//change to true for init options
let show_unclassified = true;
//variable to check if user changed anything
let is_changed = false;
//default value for k_mer_threshold
let k_mer_threshold = 0.5;

//set after init when df is given
let all_species_list = [];
let unchecked_all = false;
let checked_all = true;

// categories colors:
blue_color = "#2563eb" // blue-600 in tailwind
orange_color = "#f59e0b" // amber-500 in tailwind

let species_list = [];
let checkbox_list = [];
// dataframe of threshold by species
let df = "";
let sum_total = 0;
let sum_cols_df = 0;

let non_contaminant_col_name = "";

const initResultsScript = (data, threshold_columns_name) => {
    const json_data = JSON.parse(data);
    non_contaminant_col_name = threshold_columns_name;
    runResultsScript(json_data)
    is_changed = false;
};

//set functions
const update_species_list = (item) => {
    is_changed = true;
    if (item.checked) {
        if (!species_list.includes(item.id)) {
            species_list.push(item.id)
        }
    } else {
        if (species_list.includes(item.id)) {
            item_index = species_list.indexOf(item.id);
            species_list.splice(item_index, 1);
        }
    }
    document.getElementById("species_list_filter").value = [...species_list];
}
const update_k_mer_threshold = (new_val) => {
    is_changed = true;
    k_mer_threshold = new_val;
    document.getElementById("k_mer_threshold").value = new_val;
}


const runResultsScript = (json_data) => {
    let new_index = []
    let new_data = {}

    Object.entries(json_data).map(([key, val]) => {
        new_data[key] = Object.values(val);
        new_index = Object.keys(val);
    })
    new_index = new_index.map((item) => parseFloat(item))
    df = new dfd.DataFrame(new_data, {index: new_index});
    sum_total = df.sum({axis: 0}).sum({axis: 1});
    sum_cols_df = df.sum({axis: 1});
    //updates when pressing checkboxes
    df.columns.forEach(item => update_species_list({id: item, checked: true}))
    update_species_list({id:non_contaminant_col_name, checked: false});

    update_k_mer_threshold(k_mer_threshold)    

    Chart.register("chartjs-plugin-annotation");
    bar_chart, pie_chart = createResultsCharts()
    
    draw_kmer_hist(bar_chart, pie_chart)
    draw_species_pie_chart(pie_chart)
    draw_species_list()
}

const createResultsCharts = () => {
    bar_chart = new Chart('bar_chart', {
        type: "bar",
        data: {},
        options: {}
    });

    pie_chart = new Chart('pie_chart', {
        type: "doughnut",
        data: {},
        options: {}
    });
    return bar_chart, pie_chart;
}

const draw_species_pie_chart = (chart) => {
    
    const threshold_list = df.index.filter(item => item >= k_mer_threshold)

    let sum_classified_df = df.loc({ rows: threshold_list, columns: species_list }).sum({axis: 0});

    let sum_unclassified = sum_total - sum_classified_df.sum({axis: 1});

    let unclassified_percent = (sum_unclassified/sum_total)*100
    let classified_percent = 100 - (sum_unclassified/sum_total)*100

    chart.data.labels = ["Percent to be retained","Percent to be filtered"]
    let bins_colors = [blue_color, orange_color]
    let bins_values = [unclassified_percent, classified_percent]
    bins_values.push()

    chart.data.datasets = [{
        data: bins_values,
        hoverOffset: 4,
        backgroundColor: bins_colors
        }
    ];
    chart.options.borderRadius = 10
    chart.options.radius = "75%"
    chart.options.plugins.legend.display = false;
    chart.options.plugins.tooltip = {
        titleFont: {
            size: 24
        },
        bodyFont: {
            size: 24
        }
    }

    chart.update()
}

const draw_kmer_hist = (chart, pie_chart) => {
    let sum_classified_df = df.loc({ columns: species_list }).sum({axis: 1});
    let df_index = sum_classified_df.index;
    sum_classified_df = sum_classified_df.setIndex(df_index)
    const classified_indexes = sum_classified_df.index
    const classified_values = classified_indexes.map((index) => {

        return parseFloat(index) < k_mer_threshold ? 0 : sum_classified_df.loc([index]).values[0];
    })
    sum_classified_df = new dfd.Series(classified_values, { index: classified_indexes });
    let sum_unclassified_df = sum_cols_df.sub(sum_classified_df)
    const bins_x = df_index
    const classified_y = sum_classified_df.values
    const unclassified_y = sum_unclassified_df.values

    
    chart.data.labels = bins_x
    chart.data.datasets = [
        {
            data: classified_y,
            backgroundColor: orange_color,
            label: 'Classified as contaminant'

        }
    ];
    
    show_unclassified ? chart.data.datasets.push({
            data: unclassified_y,
            backgroundColor: blue_color,
            label: 'Classified as non-contaminant'
        }) : null;


    chart.options = {
        onHover:(event, chartElem) => {
            event.native.target.style.cursor = chartElem[0] ? "pointer" : "default";
        },
        onClick: (event) => { 

            const xTop = chart.chartArea.left;
            const xBottom = chart.chartArea.right;
            const xMin = chart.scales.x.min;
            const xMax = chart.scales.x.max;
            let newX = 0;

            if (event.x <= xBottom && event.x >= xTop) {
                newX = Math.abs((event.x - xTop) / (xBottom - xTop));
                newX = newX * (Math.abs(xMax - xMin)) + xMin;
            };
            update_k_mer_threshold(newX);
            
            draw_species_list();
            if (unchecked_all || checked_all) {
                let selection_flag = unchecked_all ? false : true;
                set_selection(selection_flag);
            } else {
                draw_kmer_hist(chart, pie_chart);
                draw_species_pie_chart(pie_chart);    
            }

        },
        plugins: {
            annotation: {
                annotations: {
                    line: {
                        type: 'line',
                        scaleID: 'x',
                        value: parseFloat(k_mer_threshold),
                        borderColor: 'rgb(255, 99, 132)',
                        borderWidth: 2,
                    }
                }
            },
            legend: {
                display: false
            },
            tooltip: {
                titleFont: {
                    size: 24
                },
                bodyFont: {
                    size: 24
                }
            }
        },
        scales: {
            x: {
                beginAtZero: true,
                stacked: true,
                type: 'linear',
                min: 0.0,
                max: 1.0,
                offset: false,
                title: {
                    display: true,
                    text: 'Read similarity to contaminated database ',
                    font: {
                        size: 24
                    }
                }
            },
            y: {
                stacked: true,
                type: 'logarithmic',
                title: {
                    display: true,
                    text: 'Number of reads (log-scale)',
                    font: {
                        size: 24
                    }
                }
            }
        }
    };

    chart.update()
}

const draw_species_list = () => {
    const species_list_container = document.getElementById("species_list");
    const threshold_list = df.index.filter(item => item >= k_mer_threshold);

    let sum_classified_df = df.loc({ rows: threshold_list}).sum({axis: 0});

    const sorted_series_by_freq = get_sorted_species_df(sum_classified_df);
        
    let zipped = _.zip(sorted_series_by_freq.index, sorted_series_by_freq.values)
    zipped = zipped.filter(val => val[1] != 0)
    const all_species = zipped.map((val) => {
        let toggle = document.createElement("label");
        toggle.classList = ["flex flex-row justify-between"]
        toggle.setAttribute("id", "toggle_" + val[0]);
        const checkbox = document.createElement("div");

        const input = document.createElement("input");
        input.setAttribute("type", "checkbox");
        input.setAttribute("id", val[0]);
        input.setAttribute("class", "h-5 w-5  accent-amber-500")
        input.checked = species_list.includes(val[0]) ? true : false;

        input.addEventListener("click", (change) => {
            const item = change.target;
            unchecked_all = false;
            checked_all = false;
            update_species_list(item);
            //update the species_list to sent to backend
            draw_kmer_hist(bar_chart, pie_chart);
            draw_species_pie_chart(pie_chart);
        });
        
        let label = document.createElement("span");
        label.innerText = val[0];
        checkbox.appendChild(input)
        checkbox.appendChild(label);
        toggle.appendChild(checkbox);

        const num_reads = document.createElement("span");
        num_reads.setAttribute("id", "numreads_" + val[0]);
        num_reads.classList = ["px-4"]
        num_reads.innerText = val[1];
        toggle.appendChild(num_reads);
        return toggle;
    });

    species_list_container.replaceChildren(...all_species)

}



// sorted species list by reads without unclassified entry
const get_sorted_species_df = (df_to_sort) => {
    let sort_index = df_to_sort.sortValues({"ascending": false }).index
    let sorted_index_by_freq = df_to_sort.loc(sort_index).index

    sorted_index_by_freq = sorted_index_by_freq.filter(item => item != non_contaminant_col_name)
    return df_to_sort.loc(sorted_index_by_freq);
}


const confirm_export = (e) => {
    if(!is_changed){
        if(!confirm(HELP_TEXT_CONFIRM_EXPORT_NO_CHANGE.trim())) {
            e.preventDefault();
        }
    }
}

document.getElementById("help_text_bar_similarites").innerText = HELP_TEXT_BAR_SIMILARITES.trim()
document.getElementById("help_text_species_list").innerText = HELP_TEXT_SPECIES_LIST.trim()
document.getElementById("help_text_pie_chart").innerText = HELP_TEXT_PIE_CHART.trim()


//download pie chart
document.getElementById("download_pie").addEventListener('click', function(){
    /*Get image of canvas element*/
    var url_base64jp = document.getElementById("pie_chart").toDataURL("image/jpg");
    /*get download button (tag: <a></a>) */
    var a =  document.getElementById("download_pie");
    /*insert chart image url to download button (tag: <a></a>) */
    a.href = url_base64jp;
});

//download histogram chart
document.getElementById("download_histogram").addEventListener('click', function(){
    /*Get image of canvas element*/
    var url_base64jp = document.getElementById("bar_chart").toDataURL("image/jpg");
    /*get download button (tag: <a></a>) */
    var a =  document.getElementById("download_histogram");
    /*insert chart image url to download button (tag: <a></a>) */
    a.href = url_base64jp;
});


const set_selection = (flag) => {
    const species_checkbox_list = [...document.getElementById("species_list").getElementsByTagName('input')];
    
    species_checkbox_list.forEach(item => {
        item.checked = flag;
        update_species_list(item);
    });
    unchecked_all = !flag;
    checked_all = flag;

    draw_kmer_hist(bar_chart, pie_chart);
    draw_species_pie_chart(pie_chart);
}

document.getElementById("select_button").addEventListener("click",() => set_selection(true))
document.getElementById("unselect_button").addEventListener("click",() => set_selection(false))

document.getElementById("download_matrix").addEventListener("click", () => {
    df.toCSV({ fileName: "matrix.csv", download: true})
});
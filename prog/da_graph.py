import matplotlib
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import math


class GraphBuilder ():

    def __init__(self, backend=None):
        if backend == None or backend == "":
            return
        else:
            matplotlib.use(backend)

    def build(self, df, options, show=True):
        #        matplotlib.use('GTK3Agg') # Error GTK3Agg
        plt.style.use(options["style"])
        fig, axis = plt.subplots(figsize=(8, 10))  # , sharex= True)
        ind = np.arange(len(df.index))
        stacked_plus = np.zeros(shape=(len(df.index)))
        stacked_neg = np.zeros(shape=(len(df.index)))
        for serie in options["series"]:
            data_array = df[serie['column']]
            if "negativ" in serie:
                data_array = np.negative(data_array)
            type = serie["type"]
            color = serie["color"]
            if "label" in serie:
                label = serie["label"]
            else:
                label = serie["column"].capitalize()
            if type == "bar":
                axis.bar(ind, data_array, label=label, color=color, align="edge")
            elif type == "line":
                linestyle = serie["linestyle"]
                axis.plot(ind, data_array, label=label, linestyle=linestyle, color=color, align="edge")
            else:  # stacked bar
                sum = np.sum(data_array)
                if sum > 0:
                    axis.bar(ind, data_array, bottom=stacked_plus, label=label, color=color, align="edge")
                    stacked_plus = stacked_plus + data_array
                elif sum < 0:
                    axis.bar(ind, data_array, bottom=stacked_neg, label=label, color=color, align="edge")
                    stacked_neg = stacked_neg + data_array

        xlabels = df[options["haxis"]["values"]].values.tolist()
        axis.set_xticks(ind, labels=xlabels, )
        axis.set_xlabel(options["haxis"]["title"])
        if len(df.index) > 8:
            axis.xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis.xaxis.set_minor_locator(ticker.MultipleLocator(1))
        if len(str(xlabels[0])) > 2:
            axis.set_xticks(axis.get_xticks(), axis.get_xticklabels(), rotation=45, ha='right')

        ylim = math.ceil(max(np.max(stacked_plus), - np.min(stacked_neg)))
        # math.ceil(max(max(accu_out_p) + max(c_l_p) + max(pv_p), -min(min(base_n), min(boiler_n), min(heatpump_n), min(ev_n), min(c_t_n), min(accu_in_n) )))
        if np.min(stacked_neg) < 0:
            axis.set_ylim([-ylim, ylim])
        else:
            axis.set_ylim([0, ylim])
        axis.set_ylabel(options["vaxis"][0]["title"])

        axis.set_title(options["title"])
        # Shrink current axis by 20%
        box = axis.get_position()
        axis.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        # Put a legend to the right of the current axis
        # axis.legend(loc = 'center left', bbox_to_anchor=(1, 0.5))
        axis.legend(loc='upper left', bbox_to_anchor=(1.05, 1.00))
        if show:
            plt.show()
        else:
            return fig

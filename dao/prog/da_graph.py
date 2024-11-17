import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import math
import logging


class GraphBuilder:

    def __init__(self, backend=None):
        plt.set_loglevel(level="warning")
        pil_logger = logging.getLogger("PIL")
        # override the logger logging level to INFO
        pil_logger.setLevel(logging.INFO)

        if backend is None or backend == "":
            return
        else:
            matplotlib.use(backend)

    @staticmethod
    def build(df, options, show=True):
        plt.style.use(options["style"])
        fig, axis = plt.subplots(figsize=(8, 8))  # , sharex= True)
        fig.subplots_adjust(bottom=0.15)
        if len(options["vaxis"]) > 1:
            axis_right = axis.twinx()
            width = 0.3
        else:
            axis_right = None
            width = 0.7
        ind = np.arange(len(df.index))
        stacked_plus = stacked_plus_right = np.zeros(shape=(len(df.index)))
        stacked_neg = stacked_neg_right = np.zeros(shape=(len(df.index)))
        labels = []
        handles = []
        for serie in options["series"]:
            if "vaxis" in serie:
                vax = serie["vaxis"]
            else:
                vax = "left"
            if vax == "left":
                ax = axis
            else:
                ax = axis_right
            if "column" in serie:
                data_array = df[serie["column"]]
            else:
                data_array = df[serie["name"]]
            if ("negativ" in serie) or (("sign" in serie) and (serie["sign"] == "neg")):
                data_array = np.negative(data_array)
            s_type = serie["type"]
            color = serie["color"]
            if "label" in serie:
                label = serie["label"]
            else:
                label = serie["column"].capitalize()
            labels.append(label)
            plot = None
            if s_type == "bar":
                plot = ax.bar(
                    ind, data_array, label=label, width=width, color=color, align="edge"
                )
            elif s_type == "line":
                linestyle = serie["linestyle"]
                plot = ax.plot(
                    ind,
                    data_array,
                    label=label,
                    linestyle=linestyle,
                    color=color,
                    align="edge",
                )
            else:  # stacked bar
                data_sum = np.sum(data_array)
                if data_sum >= 0:
                    if vax == "left":
                        plot = ax.bar(
                            ind,
                            data_array,
                            width=width,
                            bottom=stacked_plus,
                            label=label,
                            color=color,
                            align="edge",
                        )
                        stacked_plus = stacked_plus + data_array
                    else:
                        plot = ax.bar(
                            ind + width,
                            data_array,
                            width=width,
                            bottom=stacked_plus_right,
                            label=label,
                            color=color,
                            align="edge",
                        )
                        stacked_plus_right = stacked_plus_right + data_array
                elif data_sum < 0:
                    if vax == "left":
                        plot = ax.bar(
                            ind,
                            data_array,
                            width=width,
                            bottom=stacked_neg,
                            label=label,
                            color=color,
                            align="edge",
                        )
                        stacked_neg = stacked_neg + data_array
                    else:
                        plot = ax.bar(
                            ind + width,
                            data_array,
                            width=width,
                            bottom=stacked_neg_right,
                            label=label,
                            color=color,
                            align="edge",
                        )
                        stacked_neg_right = stacked_neg_right + data_array
            if plot is not None:
                handles.append(plot)

        xlabels = df[options["haxis"]["values"]].values.tolist()
        axis.set_xticks(
            ind,
            labels=xlabels,
        )
        if "title" in options["haxis"]:
            axis.set_xlabel(options["haxis"]["title"])
        if len(df.index) > 8:
            axis.xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis.xaxis.set_minor_locator(ticker.MultipleLocator(1))
        if len(str(xlabels[0])) > 2:
            axis.set_xticks(
                axis.get_xticks(), axis.get_xticklabels(), rotation=45, ha="right"
            )

        ylim = math.ceil(max(np.max(stacked_plus), -np.min(stacked_neg)))
        # math.ceil(max(max(accu_out_p) + max(c_l_p) + max(pv_p), -min(min(base_n), min(boiler_n),
        # min(heatpump_n), min(ev_n), min(c_t_n), min(accu_in_n) )))
        if np.min(stacked_neg) < 0:
            axis.set_ylim([-ylim, ylim])
        else:
            axis.set_ylim([0, ylim])
        axis.set_ylabel(options["vaxis"][0]["title"])

        if axis_right:
            ylim = math.ceil(
                max(np.max(stacked_plus_right), -np.min(stacked_neg_right))
            )
            if np.min(stacked_neg_right) < 0:
                axis_right.set_ylim([-ylim, ylim])
            else:
                axis_right.set_ylim([0, ylim])
            axis_right.set_ylabel(options["vaxis"][1]["title"])

        axis.set_title(options["title"])
        # Shrink current axis by 20%
        box = axis.get_position()
        axis.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        # Put a legend to the right of the current axis
        # axis.legend(loc = 'center left', bbox_to_anchor=(1, 0.5))
        axis.legend(
            handles=handles,
            labels=labels,
            loc="upper left",
            bbox_to_anchor=(1.05, 1.00),
        )
        if show:
            plt.show()
        else:
            return fig

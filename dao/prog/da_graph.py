import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
import pandas as pd
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
            backend = "Agg"
        matplotlib.use(backend)

    def draw_waterfall(self, axis, dr_df: pd.DataFrame, options: dict):
        """
        tekent een waterfall grafiek
        :param axis: canvas
        :param options: dict with definitions
        :param dr_df: dataframe met data
        :param y: columnnane met y-data
        :param title: titel grafiek
        :return:
        """
        y = options["series"][0]["column"]
        df = pd.DataFrame(columns=[y])
        df[y] = dr_df[y]

        total = df[y].sum()
        df.loc[df.shape[0]] = [total]

        # Calculating the running totals
        # print(df)
        df["Running_Total"] = df[y].cumsum()
        # print(df)
        df["Shifted_Total"] = df["Running_Total"].shift(1).fillna(0)
        df.loc[df.index[-1], "Shifted_Total"] = 0.0
        # print(df)

        # plotting the waterfall chart

        # code for Bars
        bw = 0.6
        ind = np.arange(len(df.index))
        plot = axis.bar(
            ind,
            df[y],
            bottom=df["Shifted_Total"],
            width=bw,
            edgecolor=["green" if x >= 0 else "red" for x in df[y]],
            color=["green" if x >= 0 else "red" for x in df[y]],
        )

        for i in range(1, len(df)):
            axis.plot(
                [(i - 1) + bw / 2, i - bw / 2],
                [df["Running_Total"].iloc[i - 1], df["Running_Total"].iloc[i - 1]],
                color="green" if df[y].iloc[i] >= 0 else "red",
            )

        max_y = math.ceil(max(max(df["Running_Total"][:-1]), 0))
        min_y = math.floor(min(min(df["Running_Total"][:-1]) - 1, 0))
        delta = math.floor((max_y - min_y) / 10)
        axis.set_ylim([min_y, max_y + delta])
        rel_y_pos_text = (max_y - min_y) / 100
        # Adding the total labels
        abs_max_y = max(max_y, -min_y, abs(df["Running_Total"].iloc[-1]))
        dec_num = 1 if abs_max_y < 10 else 0
        old_total = 0
        old_amount = None
        for i, (total, bottom, amount) in enumerate(
            zip(df["Running_Total"], df["Shifted_Total"], df[y])
        ):
            total = old_total if i == (len(df["Running_Total"]) - 1) else total
            old_total = total
            if amount != old_amount:
                axis.text(
                    i,
                    max(total, bottom) + rel_y_pos_text,
                    f"{amount:.{dec_num}f}",
                    ha="center",
                )
            old_amount = amount

        axis.set_title(options["series"][0]["title"])
        axis.set_ylabel(options["vaxis"][0]["title"])
        return plot

    def build(self, df, options, show=True):
        plt.style.use(options["style"])
        graphs = options["graphs"]
        num_graphs = len(graphs)
        fig, axis = plt.subplots(
            figsize=(8, 5 * num_graphs), nrows=num_graphs, sharex="all"
        )
        fig.subplots_adjust(bottom=0.2)
        g_nr = -1
        haxis = options["haxis"]
        for g_options in graphs:
            labels = []
            handles = []
            g_nr += 1
            if num_graphs == 1:
                ax = axis
            else:
                ax = axis[g_nr]
            if "graph_type" in g_options:
                graph_type = g_options["graph_type"]
            else:
                graph_type = "bar"
            ind = np.arange(len(df.index))
            if graph_type == "waterfall":
                axis_right = None
                stacked_plus = None
                plot = self.draw_waterfall(ax, df, g_options)
                serie = g_options["series"][0]
                if "name" in serie:
                    label = serie["name"]
                else:
                    label = serie["column"].capitalize()
                handles, labels = ax.get_legend_handles_labels()
                handles.append(Patch(facecolor="green"))
                handles.append(Patch(facecolor="red"))
                labels.append(label + " (+)")
                labels.append(label + " (-)")
            else:
                if len(g_options["vaxis"]) > 1:
                    axis_right = ax.twinx()
                    width = 0.3
                else:
                    axis_right = None
                    width = 0.7
                stacked_plus = stacked_plus_right = np.zeros(shape=(len(df.index)))
                stacked_neg = stacked_neg_right = np.zeros(shape=(len(df.index)))
                ymin_left = ymax_left = ymin_right = ymax_right = 0
                for serie in g_options["series"]:
                    if "vaxis" in serie:
                        vax = serie["vaxis"]
                    else:
                        vax = "left"
                    if vax == "right":
                        ax_serie = axis_right
                    else:
                        ax_serie = ax
                    if "column" in serie:
                        data_array = df[serie["column"]]
                    else:
                        data_array = df[serie["name"]]
                    data_array = pd.to_numeric(data_array)
                    if "width" in serie:
                        width = serie["width"]
                    data_array = data_array.to_list()
                    if ("negativ" in serie) or (
                        ("sign" in serie) and (serie["sign"] == "neg")
                    ):
                        data_array = np.negative(data_array)
                    s_type = serie["type"]
                    color = serie["color"]
                    if "name" in serie:
                        label = serie["name"]
                    else:
                        label = serie["column"].capitalize()
                    labels.append(label)
                    plot = None
                    if vax == "left":
                        ymax_left = math.ceil(max(ymax_left, max(data_array)))
                        ymin_left = math.floor(min(ymin_left, min(data_array)))
                    if vax == "right":
                        ymax_right = math.ceil(max(ymax_right, max(data_array)))
                        ymin_right = math.floor(min(ymin_right, min(data_array)))

                    if s_type == "bar":
                        plot = ax_serie.bar(
                            ind,
                            data_array,
                            label=label,
                            width=width,
                            color=color,
                            align="edge",
                        )
                    elif s_type == "line":
                        if "linestyle" in serie:
                            linestyle = serie["linestyle"]
                        else:
                            linestyle = "solid"
                        plot = ax_serie.plot(
                            ind,
                            data_array,
                            label=label,
                            linestyle=linestyle,
                            color=color
                        )[0]
                    elif s_type == "step":
                        if "linestyle" in serie:
                            linestyle = serie["linestyle"]
                        else:
                            linestyle = "solid"
                        data_array.append(data_array[-1])
                        ind_serie = np.arange(len(ind) + 1)
                        plot = ax_serie.step(
                            ind_serie,
                            data_array,
                            label=label,
                            linestyle=linestyle,
                            color=color,
                            where="post",
                        )[0]
                    elif s_type == "stacked":
                        data_sum = np.sum(data_array)
                        if data_sum >= 0:
                            if vax == "left":
                                plot = ax_serie.bar(
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
                                plot = ax_serie.bar(
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
                                plot = ax_serie.bar(
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
                                plot = ax_serie.bar(
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

            xlabels = df[haxis["values"]].values.tolist()
            if graph_type == "waterfall":
                ind = np.arange(len(df.index) + 1)
                xlabels += ["Totaal"]

            ax.set_xticks(
                ind,
                labels=xlabels,
            )
            if "title" in haxis and g_nr == (num_graphs - 1):
                ax.set_xlabel(haxis["title"])
            num_xas = len(df.index)
            if num_xas > 12:
                ax.xaxis.set_major_locator(ticker.MultipleLocator(round(num_xas/12)))
                ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
            if len(str(xlabels[0])) > 2:
                ax.set_xticks(
                    ax.get_xticks(), ax.get_xticklabels(), rotation=45, ha="right"
                )
            if g_nr == 0:
                ax.set_title(options["title"])
            # Shrink current axis by 20%
            box = ax.get_position()
            ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
            # Put a legend to the right of the current axis
            # axis.legend(loc = 'center left', bbox_to_anchor=(1, 0.5))

            if axis_right:
                ylim = math.ceil(
                    max(np.max(stacked_plus_right), -np.min(stacked_neg_right))
                )
                if ylim > 0:
                    if np.min(stacked_neg_right) < 0:
                        axis_right.set_ylim([-ylim, ylim])
                    else:
                        axis_right.set_ylim([0, ylim])
                else:
                    axis_right.set_ylim([min(0, ymin_right), ymax_right])
                axis_right.set_ylabel(g_options["vaxis"][1]["title"])

            if stacked_plus is not None:
                ylim = math.ceil(max(np.max(stacked_plus), -np.min(stacked_neg)))
                if ylim > 0:
                    if np.min(stacked_neg) < 0:
                        ax.set_ylim([-ylim, ylim])
                    else:
                        ax.set_ylim([0, ylim])
                else:
                    ax.set_ylim([min(0, ymin_left), ymax_left])
                ax.set_ylabel(g_options["vaxis"][0]["title"])

            ax.legend(
                handles=handles,
                labels=labels,
                loc="upper left",
                bbox_to_anchor=(1.05, 1.00),
            )

        if show:
            plt.show()
        else:
            return fig

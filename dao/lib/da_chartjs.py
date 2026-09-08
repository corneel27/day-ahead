"""
Chart.js counterpart of :class:`dao.lib.da_graph.GraphBuilder`.

Both builders consume the same declarative ``options`` dictionaries that are
defined in :mod:`dao.prog.da_report`. Where ``GraphBuilder`` rasterizes those
options into a matplotlib figure, ``ChartSpecBuilder`` turns them into a
JSON-serializable specification that the browser renders with Chart.js, so the
V2 GUI shows interactive charts instead of static images.
"""

import logging
import math

import pandas as pd

# Used when a serie in the options carries no explicit colour.
FALLBACK_COLORS = [
    "#00bfff",
    "#2e7d32",
    "#dc3545",
    "#ff8000",
    "#a32cc4",
    "#0d6efd",
    "#20c997",
    "#f9a825",
]

WATERFALL_POSITIVE_COLOR = "green"
WATERFALL_NEGATIVE_COLOR = "red"
WATERFALL_TOTAL_LABEL = "Totaal"

LEFT_AXIS = "y_left"
RIGHT_AXIS = "y_right"


def _to_json_value(value):
    """Convert a single pandas/numpy value to something ``json`` can encode."""
    if value is None or pd.isna(value):
        return None
    value = float(value)
    if math.isinf(value):
        return None
    return round(value, 3)


class ChartSpecBuilder:
    """Builds a Chart.js specification from a dataframe and graph options."""

    def build(self, df: pd.DataFrame, options: dict) -> dict:
        """
        :param df: dataframe with the data, one row per x-value
        :param options: the same options dict that ``GraphBuilder.build`` takes
        :return: a JSON-serializable dict with a ``graphs`` list; every entry
            describes one canvas (labels, datasets and axes)
        """
        haxis = options.get("haxis", {})
        labels = self._get_labels(df, haxis)

        graphs = []
        for graph_options in options.get("graphs", []):
            if graph_options.get("graph_type") == "waterfall":
                graphs.append(self._build_waterfall(df, graph_options, labels))
            else:
                graphs.append(self._build_graph(df, graph_options, labels))

        return {
            "title": options.get("title", ""),
            "haxis_title": haxis.get("title"),
            "graphs": graphs,
        }

    @staticmethod
    def _get_labels(df: pd.DataFrame, haxis: dict) -> list:
        column = haxis.get("values")
        if column is None or column not in df.columns:
            return [str(index) for index in df.index]
        return [str(value) for value in df[column].tolist()]

    @staticmethod
    def _get_series_values(df: pd.DataFrame, serie: dict) -> list | None:
        column = serie.get("column", serie.get("name"))
        if column is None or column not in df.columns:
            logging.warning(f"Kolom '{column}' ontbreekt in de rapportagedata")
            return None

        values = pd.to_numeric(df[column], errors="coerce")
        # Same convention as GraphBuilder: the dataframe holds magnitudes, the
        # options say on which side of the zero line they belong.
        if ("negativ" in serie) or (serie.get("sign") == "neg"):
            values = -values

        return [_to_json_value(value) for value in values.tolist()]

    @staticmethod
    def _axis_id(serie: dict) -> str:
        return RIGHT_AXIS if serie.get("vaxis") == "right" else LEFT_AXIS

    @staticmethod
    def _get_label(serie: dict) -> str:
        return (
            serie.get("title")
            or serie.get("name")
            or serie.get("column", "").capitalize()
        )

    @staticmethod
    def _get_unit(vaxis: list, axis_id: str) -> str:
        axis_index = 1 if axis_id == RIGHT_AXIS else 0
        if axis_index >= len(vaxis):
            return ""
        return vaxis[axis_index].get("title", "")

    def _build_graph(self, df: pd.DataFrame, graph_options: dict, labels: list) -> dict:
        vaxis = graph_options.get("vaxis", [{}])

        datasets = []
        stacked_axes = set()

        for index, serie in enumerate(graph_options.get("series", [])):
            values = self._get_series_values(df, serie)
            if values is None:
                continue

            serie_type = serie.get("type", "bar")
            axis_id = self._axis_id(serie)
            color = serie.get("color") or FALLBACK_COLORS[index % len(FALLBACK_COLORS)]

            dataset = {
                "label": self._get_label(serie),
                "data": values,
                "borderColor": color,
                "backgroundColor": color,
                "yAxisID": axis_id,
                "unit": self._get_unit(vaxis, axis_id),
            }

            if serie_type in ("line", "step"):
                dataset["type"] = "line"
                dataset["fill"] = False
                dataset["pointRadius"] = 0
                dataset["borderWidth"] = 2
                if serie.get("linestyle") == "dashed":
                    dataset["borderDash"] = [6, 4]
                if serie_type == "step":
                    # GraphBuilder draws post-steps on an axis whose ticks mark
                    # the start of an interval, and repeats the last value to
                    # fill the final one. Chart.js centres its categories, so
                    # "middle" is the equivalent: every category, the last one
                    # included, gets a horizontal run centred on its tick, in
                    # line with where the bars are drawn.
                    dataset["stepped"] = "middle"
            else:
                dataset["type"] = "bar"
                if serie_type == "stacked":
                    # All stacked series on one axis share a stack; Chart.js
                    # keeps positive and negative values apart by itself.
                    dataset["stack"] = axis_id
                    stacked_axes.add(axis_id)
                else:
                    # A plain bar gets its own stack so it stays side by side,
                    # even when the axis is stacked for other series.
                    dataset["stack"] = f"{axis_id}_{index}"

            datasets.append(dataset)

        # GraphBuilder centres an axis on zero as soon as that axis holds
        # negative values, and starts it at zero otherwise. Deciding this per
        # graph instead of per axis is the one deliberate difference: it is what
        # the "align_zeros" option asks for, and it keeps the zero line of the
        # left and the right axis at the same height when only one of the two
        # goes negative.
        has_negative = any(
            value is not None and value < 0
            for dataset in datasets
            for value in dataset["data"]
        )

        return {
            "labels": labels,
            "datasets": datasets,
            "axes": self._build_axes(
                datasets,
                vaxis,
                stacked_axes,
                align_zero=has_negative,
                begin_at_zero=not has_negative,
            ),
        }

    def _build_waterfall(
        self, df: pd.DataFrame, graph_options: dict, labels: list
    ) -> dict:
        serie = graph_options["series"][0]
        vaxis = graph_options.get("vaxis", [{}])
        unit = vaxis[0].get("title", "")

        values = self._get_series_values(df, serie)
        if values is None:
            values = []

        amounts = [value or 0.0 for value in values]
        total = sum(amounts)

        bars = []
        running_totals = []
        colors = []
        running = 0.0
        for amount in amounts:
            bars.append([round(running, 3), round(running + amount, 3)])
            running += amount
            running_totals.append(round(running, 3))
            colors.append(
                WATERFALL_POSITIVE_COLOR if amount >= 0 else WATERFALL_NEGATIVE_COLOR
            )

        # Closing bar with the grand total, drawn from zero.
        bars.append([0, round(total, 3)])
        running_totals.append(round(total, 3))
        colors.append(
            WATERFALL_POSITIVE_COLOR if total >= 0 else WATERFALL_NEGATIVE_COLOR
        )

        datasets = [
            {
                "type": "bar",
                "label": self._get_label(serie),
                "data": bars,
                "backgroundColor": colors,
                "borderColor": colors,
                "yAxisID": LEFT_AXIS,
                "unit": unit,
                "waterfall": True,
                "amounts": [round(amount, 3) for amount in amounts] + [round(total, 3)],
            },
            {
                "type": "line",
                "label": "Cumulatief",
                "data": running_totals,
                "borderColor": "#888888",
                "backgroundColor": "#888888",
                "borderDash": [4, 4],
                "borderWidth": 1,
                "pointRadius": 0,
                "stepped": "middle",
                "fill": False,
                "yAxisID": LEFT_AXIS,
                "unit": unit,
            },
        ]

        return {
            "labels": labels + [WATERFALL_TOTAL_LABEL],
            "datasets": datasets,
            # The bars float on the running total, so the axis must still show
            # where zero is.
            "axes": self._build_axes(
                datasets, vaxis, set(), align_zero=False, begin_at_zero=True
            ),
        }

    @staticmethod
    def _build_axes(
        datasets: list,
        vaxis: list,
        stacked_axes: set,
        align_zero: bool,
        begin_at_zero: bool = False,
    ) -> list:
        axes = []
        for axis_index, axis_id in enumerate((LEFT_AXIS, RIGHT_AXIS)):
            if not any(dataset["yAxisID"] == axis_id for dataset in datasets):
                continue

            title = ""
            if axis_index < len(vaxis):
                title = vaxis[axis_index].get("title", "")

            axes.append({
                "id": axis_id,
                "title": title,
                "position": "left" if axis_id == LEFT_AXIS else "right",
                "stacked": axis_id in stacked_axes,
                "align_zero": align_zero,
                "begin_at_zero": begin_at_zero,
            })

        return axes

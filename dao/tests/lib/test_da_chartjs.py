import pandas as pd
import pytest

from dao.lib.da_chartjs import ChartSpecBuilder, LEFT_AXIS, RIGHT_AXIS


@pytest.fixture
def grid_df():
    return pd.DataFrame(
        {
            "Uur": ["00:00", "01:00", "02:00"],
            "Verbruik": [1.0, 2.0, 0.5],
            "Productie": [0.0, 0.5, 3.0],
            "Kosten": [0.25, 0.5, 0.1],
            "Opbrengst": [0.0, 0.1, 0.6],
        }
    )


@pytest.fixture
def grid_options():
    return {
        "title": "Verbruik en kosten vandaag",
        "style": "default",
        "haxis": {"values": "Uur", "title": "uur"},
        "graphs": [
            {
                "vaxis": [{"title": "kWh"}, {"title": "euro"}],
                "series": [
                    {
                        "column": "Verbruik",
                        "title": "Verbruik",
                        "type": "stacked",
                        "color": "#00bfff",
                    },
                    {
                        "column": "Productie",
                        "title": "Productie",
                        "negativ": "true",
                        "type": "stacked",
                        "color": "green",
                    },
                    {
                        "column": "Kosten",
                        "title": "Kosten",
                        "type": "stacked",
                        "color": "red",
                        "vaxis": "right",
                    },
                ],
            }
        ],
    }


def get_dataset(graph, label):
    return next(ds for ds in graph["datasets"] if ds["label"] == label)


def get_axis(graph, axis_id):
    return next(axis for axis in graph["axes"] if axis["id"] == axis_id)


class TestBuild:
    def test_title_and_labels(self, grid_df, grid_options):
        spec = ChartSpecBuilder().build(grid_df, grid_options)

        assert spec["title"] == "Verbruik en kosten vandaag"
        assert spec["haxis_title"] == "uur"
        assert len(spec["graphs"]) == 1
        assert spec["graphs"][0]["labels"] == ["00:00", "01:00", "02:00"]

    def test_labels_fall_back_to_the_index(self, grid_df, grid_options):
        grid_options["haxis"] = {"values": "ontbreekt"}
        spec = ChartSpecBuilder().build(grid_df, grid_options)

        assert spec["graphs"][0]["labels"] == ["0", "1", "2"]

    def test_series_values_are_taken_from_the_column(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["data"] == [1.0, 2.0, 0.5]

    def test_negativ_series_are_mirrored(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Productie")["data"] == [0.0, -0.5, -3.0]

    def test_sign_neg_series_are_mirrored(self, grid_df, grid_options):
        grid_options["graphs"][0]["series"][1] = {
            "column": "Productie",
            "name": "Productie",
            "sign": "neg",
            "type": "stacked",
            "color": "green",
        }
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Productie")["data"] == [0.0, -0.5, -3.0]

    def test_missing_column_is_skipped(self, grid_df, grid_options):
        grid_options["graphs"][0]["series"].append(
            {"column": "bestaat_niet", "title": "Onbekend", "type": "line"}
        )
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert [dataset["label"] for dataset in graph["datasets"]] == [
            "Verbruik",
            "Productie",
            "Kosten",
        ]

    def test_missing_values_become_null(self, grid_df, grid_options):
        grid_df.loc[1, "Verbruik"] = pd.NA
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["data"] == [1.0, None, 0.5]

    def test_series_are_assigned_to_the_configured_axis(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["yAxisID"] == LEFT_AXIS
        assert get_dataset(graph, "Kosten")["yAxisID"] == RIGHT_AXIS

    def test_axis_units_end_up_on_the_datasets(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["unit"] == "kWh"
        assert get_dataset(graph, "Kosten")["unit"] == "euro"

    def test_stacked_series_share_a_stack_per_axis(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["stack"] == LEFT_AXIS
        assert get_dataset(graph, "Productie")["stack"] == LEFT_AXIS
        assert get_dataset(graph, "Kosten")["stack"] == RIGHT_AXIS

        assert get_axis(graph, LEFT_AXIS)["stacked"] is True
        assert get_axis(graph, RIGHT_AXIS)["stacked"] is True

    def test_plain_bars_keep_their_own_stack(self, grid_df, grid_options):
        grid_options["graphs"][0]["series"][0]["type"] = "bar"
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["stack"] != LEFT_AXIS
        assert get_dataset(graph, "Productie")["stack"] == LEFT_AXIS

    def test_an_axis_without_stacked_series_is_not_stacked(self, grid_df, grid_options):
        for serie in grid_options["graphs"][0]["series"]:
            serie["type"] = "line"
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_axis(graph, LEFT_AXIS)["stacked"] is False

    def test_line_and_step_series(self, grid_df, grid_options):
        grid_options["graphs"][0]["series"][0]["type"] = "line"
        grid_options["graphs"][0]["series"][1]["type"] = "step"
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["type"] == "line"
        assert "stepped" not in get_dataset(graph, "Verbruik")
        # "middle" keeps the run of the last category on the chart; "after"
        # would drop it, because a category scale ends at the last tick.
        assert get_dataset(graph, "Productie")["stepped"] == "middle"

    def test_axes_carry_title_and_position(self, grid_df, grid_options):
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_axis(graph, LEFT_AXIS)["title"] == "kWh"
        assert get_axis(graph, LEFT_AXIS)["position"] == "left"
        assert get_axis(graph, RIGHT_AXIS)["title"] == "euro"
        assert get_axis(graph, RIGHT_AXIS)["position"] == "right"

    def test_negative_values_centre_every_axis_on_zero(self, grid_df, grid_options):
        # "Productie" is mirrored, "Kosten" on the right axis is not, so only
        # the left axis goes negative. Both axes are still centred, otherwise
        # the two zero lines would sit at a different height.
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert min(get_dataset(graph, "Productie")["data"]) < 0
        assert min(get_dataset(graph, "Kosten")["data"]) >= 0

        for axis_id in (LEFT_AXIS, RIGHT_AXIS):
            assert get_axis(graph, axis_id)["align_zero"] is True
            assert get_axis(graph, axis_id)["begin_at_zero"] is False

    def test_without_negative_values_the_axes_start_at_zero(
        self, grid_df, grid_options
    ):
        del grid_options["graphs"][0]["series"][1]["negativ"]
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        for axis_id in (LEFT_AXIS, RIGHT_AXIS):
            assert get_axis(graph, axis_id)["align_zero"] is False
            assert get_axis(graph, axis_id)["begin_at_zero"] is True

    def test_unused_axis_is_left_out(self, grid_df, grid_options):
        del grid_options["graphs"][0]["series"][2]
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert [axis["id"] for axis in graph["axes"]] == [LEFT_AXIS]

    def test_multiple_graphs(self, grid_df, grid_options):
        grid_options["graphs"].append(
            {
                "vaxis": [{"title": "eur"}],
                "series": [{"column": "Kosten", "title": "Kosten", "type": "line"}],
            }
        )
        spec = ChartSpecBuilder().build(grid_df, grid_options)

        assert len(spec["graphs"]) == 2
        assert len(spec["graphs"][1]["datasets"]) == 1

    def test_series_without_colour_gets_one(self, grid_df, grid_options):
        del grid_options["graphs"][0]["series"][0]["color"]
        graph = ChartSpecBuilder().build(grid_df, grid_options)["graphs"][0]

        assert get_dataset(graph, "Verbruik")["backgroundColor"]

    def test_empty_dataframe(self, grid_options):
        empty_df = pd.DataFrame(
            columns=["Uur", "Verbruik", "Productie", "Kosten", "Opbrengst"]
        )
        graph = ChartSpecBuilder().build(empty_df, grid_options)["graphs"][0]

        assert graph["labels"] == []
        assert get_dataset(graph, "Verbruik")["data"] == []


@pytest.fixture
def saving_options():
    return {
        "title": "Besparing kosten door batterij deze week",
        "style": "default",
        "haxis": {"values": "Dag", "title": "dag"},
        "graphs": [
            {
                "graph_type": "waterfall",
                "vaxis": [{"title": "eur"}],
                "series": [
                    {"column": "saving", "title": "Besparing", "name": "Besparing"}
                ],
            }
        ],
    }


class TestWaterfall:
    @pytest.fixture
    def saving_df(self):
        return pd.DataFrame(
            {
                "Dag": ["2026-09-01", "2026-09-02", "2026-09-03"],
                "saving": [2.0, -0.5, 1.5],
            }
        )

    def test_a_total_column_is_appended(self, saving_df, saving_options):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["labels"] == ["2026-09-01", "2026-09-02", "2026-09-03", "Totaal"]

    def test_bars_run_from_the_running_total(self, saving_df, saving_options):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["datasets"][0]["data"] == [
            [0.0, 2.0],
            [2.0, 1.5],
            [1.5, 3.0],
            [0, 3.0],
        ]

    def test_bar_colours_follow_the_sign(self, saving_df, saving_options):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["datasets"][0]["backgroundColor"] == [
            "green",
            "red",
            "green",
            "green",
        ]

    def test_amounts_are_kept_for_the_tooltip(self, saving_df, saving_options):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["datasets"][0]["amounts"] == [2.0, -0.5, 1.5, 3.0]

    def test_running_total_line(self, saving_df, saving_options):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["datasets"][1]["data"] == [2.0, 1.5, 3.0, 3.0]

    def test_missing_values_count_as_zero(self, saving_df, saving_options):
        saving_df.loc[1, "saving"] = pd.NA
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert graph["datasets"][0]["amounts"] == [2.0, 0.0, 1.5, 3.5]

    def test_waterfall_axis_starts_at_zero_and_is_not_centred(
        self, saving_df, saving_options
    ):
        graph = ChartSpecBuilder().build(saving_df, saving_options)["graphs"][0]

        assert get_axis(graph, LEFT_AXIS)["align_zero"] is False
        assert get_axis(graph, LEFT_AXIS)["begin_at_zero"] is True
        assert get_axis(graph, LEFT_AXIS)["title"] == "eur"

    def test_empty_dataframe(self, saving_options):
        empty_df = pd.DataFrame(columns=["Dag", "saving"])
        graph = ChartSpecBuilder().build(empty_df, saving_options)["graphs"][0]

        assert graph["labels"] == ["Totaal"]
        assert graph["datasets"][0]["data"] == [[0, 0.0]]

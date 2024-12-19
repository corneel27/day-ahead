import matplotlib.pyplot as plt
import numpy as np

# maak een figuur aan en assen om op te plotten


def make_graph_meteo(df, file=None, show=False):
    plt.figure(figsize=(15, 10))
    df["gr"] = df["gr"].astype(float)
    x_axis = np.arange(len(df["tijd_nl"].values))
    plt.bar(x_axis - 0.1, df["gr"].values, width=0.2, label="global rad")
    plt.bar(x_axis + 0.1, df["solar_rad"].values, width=0.2, label="netto rad")
    plt.xticks(x_axis + 0.1, df["tijd_nl"].values, rotation=45)
    if file is not None:
        plt.savefig(file)
    if show:
        plt.show()
    plt.close("all")
    return


def make_graph_entsoe(df):
    plt.figure(figsize=(15, 10))
    df["gr"] = df["gr"].astype(float)
    x_axis = np.arange(len(df["tijd_nl"].values))
    plt.bar(x_axis - 0.1, df["gr"].values, width=0.2, label="global rad")
    plt.bar(x_axis + 0.1, df["solar_rad"].values, width=0.2, label="netto rad")
    plt.xticks(x_axis, df["tijd_nl"].values, rotation=45)
    plt.show()
    plt.close("all")
    return

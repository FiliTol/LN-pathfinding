import time
import random
from multiprocessing import Pool
import pandas as pd
import json
import re
from random import sample
from typing import Tuple

from pandas import DataFrame


# Import data
def json_to_pd(data: str) -> tuple[DataFrame, DataFrame]:
    """
    :param data: provide json path
    :return:     pd.DataFrame for nodes and channels, as required
    """
    with open(data) as f:
        d = json.load(f)
    df_nodes, df_channels = pd.DataFrame(d["nodes"]), pd.DataFrame(d["edges"])
    return df_nodes, df_channels


def _filter_dates(pd_object: DataFrame) -> DataFrame:
    """
    This method filters out the entries with no update time, thus
    not useful.
    :param pd_object: nodes or channels dataframe to be filtered
    :return: pandas dataframe with filtered rows
    """
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit="s")
    pd_object = pd_object[pd_object.loc[:, "last_update"] > "1970-01-01"]
    return pd.DataFrame(pd_object)


# --------------------------------
# Nodes initial dataset cleaning |
# --------------------------------

def _allocate_code(addresses: list[str]) -> int:
    """
    Provides a code for the connection type used by the node, provided
    the list of Ip addresses used by the node.
    :param addresses: list of strings with Ip or onion addresses
    :return: score for the kind of addresses used by the node.
             1 of only onion, 2 if only clearnet, 3 if both onion and clearnet
             The score is independent from the number of addresses of each kind
    """
    code = []
    onion_pattern = re.compile(r".*\.onion")
    for element in addresses:
        if onion_pattern.match(element):
            code.append(1)
        else:
            code.append(2)
    return sum(set(code))


def _node_addresses(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: pandas dataframe for nodes
    :return: cleaned pandas dataframe for nodes
    """
    # Ip addresses
    pd_object.loc[:, "addresses"] = pd_object.iloc[:, 3].apply(
        lambda x: [i["addr"] for i in x]
    )
    try:
        pd_object.loc[:, "addresses"] = pd_object.loc[:, "addresses"].apply(_allocate_code)
    except:
        print("Address not found, going ahead without addresses creation")
        pass

    return pd_object


def nodes_cleaning(pd_object: DataFrame) -> DataFrame:
    pd_object = _node_addresses(_filter_dates(pd_object))
    pd_object = pd_object.filter(
        items=[
            "pub_key",
            "alias",
            "addresses"
        ]
    )
    return pd_object.set_index("pub_key")


# -----------------------------------
# Channels initial dataset cleaning |
# -----------------------------------

def _channel_filtering(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: pandas dataframe for channels
    :return: cleaned pandas dataframe for channels
    """
    pd_object = pd_object[
        pd.notnull(pd_object.loc[:, "node1_policy"]) & pd.notnull(pd_object.loc[:, "node2_policy"])
        ]

    return pd_object


def _fees_extraction(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: raw dataframe of channels with raw fees
    :return: fees extraction for dataframe of channels
    """
    # Extract base fee values
    pd_object["node1_fee_base_msat"] = pd_object["node1_policy"].apply(
        lambda x: x["fee_base_msat"]
    )
    pd_object["node2_fee_base_msat"] = pd_object["node2_policy"].apply(
        lambda x: x["fee_base_msat"]
    )
    # Extract fee rate values
    pd_object["node1_fee_rate_milli_msat"] = pd_object["node1_policy"].apply(
        lambda x: x["fee_rate_milli_msat"]
    )
    pd_object["node2_fee_rate_milli_msat"] = pd_object["node2_policy"].apply(
        lambda x: x["fee_rate_milli_msat"]
    )
    return pd_object


def _channel_data_types(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: raw dataframe of channels
    :return: new datatypes i channels dataframe
    """
    # Change data type
    pd_object["node1_fee_base_msat"] = pd_object["node1_fee_base_msat"].astype(int)
    pd_object["node2_fee_base_msat"] = pd_object["node2_fee_base_msat"].astype(int)

    pd_object["node1_fee_rate_milli_msat"] = pd_object["node1_fee_rate_milli_msat"].astype(int)
    pd_object["node2_fee_rate_milli_msat"] = pd_object["node2_fee_rate_milli_msat"].astype(int)

    pd_object.loc[:, "capacity"] = pd_object.loc[:, "capacity"].astype(int)

    return pd_object


def channels_cleaning(pd_object: DataFrame) -> DataFrame:
    pd_object = _filter_dates(pd_object)
    pd_object = _channel_filtering(pd_object)
    pd_object = _fees_extraction(pd_object)
    pd_object = _channel_data_types(pd_object)
    pd_object = pd_object.filter(
        items=[
            "channel_id",
            "node1_pub",
            "node2_pub",
            "capacity",
            "node1_fee_base_msat",
            "node1_fee_rate_milli_msat",
            "node2_fee_base_msat",
            "node2_fee_rate_milli_msat",
        ]
    )
    return pd_object.set_index("channel_id")


# ------------------------------------------------------------------
# Functions to execute in parallel the channel discovery for nodes |
# ------------------------------------------------------------------

def _nodes_df_splitting(pd_object: DataFrame, n: int) -> list[DataFrame]:
    """
    :param pd_object: nodes dataframe
    :param n: number of chunks desired to split the dataframe
    :return: list of dataframe of length==n
    """
    results = []
    splitting: int = len(pd_object) // n
    for i in range(n):
        ris = pd_object[i * splitting: (i + 1) * splitting]
        results.append(ris)
    if len(pd_object) % n != 0:
        ris = pd_object[n * splitting: len(pd_object)-1]
        results.append(ris)
    return results


def _find_channels(n, df_channels: DataFrame) -> list[str]:
    """
    :param n: node pub key
    :return: list of channels for the node
    Note that the listed channels are directed channels
    that have also a mirrored channel that describes the
    flow of funds in the opposite direction.
    Thus, this channels list is later adapted to other
    flow of channels by considering the channels
    with id "INV<channel_id>"
    """
    channels_list = []
    for c in df_channels.index:
        if df_channels.loc[c, "node1_pub"] == n.name or df_channels.loc[c, "node2_pub"] == n.name:
            channels_list.append(c)
    return channels_list


def _parallel_channel_finding(args: tuple[DataFrame, int], df_channels: DataFrame) -> DataFrame:
    dfs, i = args
    df = dfs[i].copy()
    df["outgoing_channels"] = df.apply(_find_channels, args=(df_channels,), axis=1)
    return pd.DataFrame(df)


def _append_inv_channel(c: list[str]) -> list[str]:
    ris = []
    for i in c:
        ris.append("INV" + str(i))
    return ris


def _flipped_channels(pd_object: DataFrame) -> DataFrame:
    pd_object["incoming_channels"] = pd_object["outgoing_channels"].apply(_append_inv_channel)
    return pd_object


def _drop_not_connected(df_nodes: DataFrame, df_channels: DataFrame) -> DataFrame:
    """
    :param df_nodes: nodes dataframe
    :param df_channels: channels dataframe
    :return: filtered nodes dataframe containing only the nodes
     that appear at least once in the channels dataframe
    """
    df_nodes = df_nodes[df_nodes.index.isin(df_channels["node1_pub"]) | df_nodes.index.isin(df_channels["node2_pub"])]
    return df_nodes


def split_compute_concat(df_nodes: DataFrame, df_channels: DataFrame, slices: int) -> DataFrame:
    """
    :param df_nodes: nodes dataframe before splitting
    :param df_channels: channels dataframe
    :param slices: number of slices to split the nodes df into
    :return: nodes dataframe with the new columns computed after splitting
    """
    pd_object = _drop_not_connected(df_nodes, df_channels)
    dataframes = _nodes_df_splitting(pd_object, slices)

    # Compute in parallel the channel finding and appending of channels list
    pool = Pool()
    inputs: list = [((dataframes, y), df_channels) for y in range(slices)]
    outputs: list = pool.starmap(_parallel_channel_finding, inputs)
    pd_object = _flipped_channels(pd.concat(outputs))

    return pd_object


# ------------------------------------------------
# Directed edges creation for channels dataframe |
# ------------------------------------------------

def _channel_directed_edges_creation(pd_object: DataFrame) -> DataFrame:
    """
    This function transforms the channels dataframe into a dataframe with the directed
    relationships between peers and keep only the fee charged for going trough the specific
    directed path.
    :param pd_object: channels dataframe
    :return: dataframe of channels with directed relationships and features
    """

    # Copy dataframe flip nodes
    pd_object.reset_index(inplace=True)
    pd_object1 = pd_object.copy()
    pd_object1["channel_id"] = "INV" + pd_object1["channel_id"]
    pd_object1["node1_pub"] = pd_object["node2_pub"]
    pd_object1["node2_pub"] = pd_object["node1_pub"]
    pd_object1["node2_fee_base_msat"] = pd_object["node1_fee_base_msat"]
    pd_object1["node2_fee_rate_milli_msat"] = pd_object["node1_fee_rate_milli_msat"]

    pd_object = pd.concat([pd_object, pd_object1])
    pd_object = pd_object.filter(
        items=["channel_id", "node1_pub", "node2_pub", "capacity", "node2_fee_base_msat", "node2_fee_rate_milli_msat"])
    pd_object.rename(
        columns={"node2_fee_base_msat": "fee_base_msat", "node2_fee_rate_milli_msat": "fee_rate_milli_msat"},
        inplace=True)

    return pd_object.set_index("channel_id")


def _fees_amount_conversion(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: channels dataframe
    :return: channels dataframe with converted fees
    """
    # Turn channel capacity into millisats
    pd_object["capacity"] = pd_object["capacity"]

    # Transform fees accordingly
    pd_object["fee_base_msat"] = pd_object["fee_base_msat"]/1000
    pd_object["fee_rate_milli_msat"] = pd_object["fee_rate_milli_msat"] / 1000000
    pd_object.rename(columns={"fee_base_msat": "base_fee", "fee_rate_milli_msat": "rate_fee"}, inplace=True)
    return pd_object


def directed_channels_final(pd_object: DataFrame) -> DataFrame:
    """
    :param pd_object: channels dataframe
    :return: directed channel dataframe with adjusted fees
    """
    pd_object = _channel_directed_edges_creation(pd_object)
    pd_object = _fees_amount_conversion(pd_object)

    return pd_object


def create_demand(pd_object: DataFrame, amount: int) -> DataFrame:
    """
    This function assigns the role of sender and receiver to
    two random nodes in the network
    :param pd_object: nodes dataframe
    :param amount: int representing the amount in sats
    :return: nodes dataset with demand column
    """
    random.seed(874631)
    counterparties = sample(pd_object.index.to_list(), 2)
    sender = counterparties[0]
    receiver = counterparties[1]
    # Amounts in millisat (aka 10'000'000 is 10'000 sats)

    print(f"Transaction of {amount} sats.")
    print(f"Sender: {pd_object[pd_object.index == sender]['alias'].item()}")
    print(f"Receiver: {pd_object[pd_object.index == receiver]['alias'].item()}.")

    pd_object["demand"] = 0
    pd_object.loc[pd_object.index == sender, "demand"] = -amount
    pd_object.loc[pd_object.index == receiver, "demand"] = amount

    return pd_object


def group_channels(df_channels: DataFrame) -> DataFrame:
    """
    Note that the following are arbitrary policies, that can be changed as needed.
    Deal with multi-edges (aka multiple channels between two peers):
    - average rate fee
    - average base fee,
    - average capacity
    - keep one of the two channel ids
    :return: channels dataframe withoud multiedges
    """
    aggregation_dict = {
        "channel_id": "first",
        "rate_fee": "mean",
        "base_fee": "mean",
        "capacity": "sum"
    }
    df_channels.reset_index(inplace=True)
    df_channels = df_channels.groupby(["node1_pub", "node2_pub"]).agg(aggregation_dict)
    df_channels.reset_index(inplace=True)
    df_channels.set_index("channel_id", inplace=True)
    return df_channels


if __name__ == "__main__":
    start = time.time()
    print("Cleaning script started")
    nodes, channels = json_to_pd("data/mock/mock_dataset.json")
    nodes = nodes_cleaning(nodes)
    channels = channels_cleaning(channels)

    print("Working on the parallel multiprocess channel search. Please wait without interrupting.")
    nodes = split_compute_concat(nodes, channels, slices=7)

    channels = directed_channels_final(channels)

    nodes.to_pickle("data/mock/mock_nodes.pkl")
    channels.to_pickle("data/mock/mock_channels.pkl")
    print("Dataframes saved as pickles in the data/ folder")

    end = time.time()
    print(f"It took {end - start} seconds to execute the whole script.")
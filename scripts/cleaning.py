import random
from multiprocessing import Pool
import pandas as pd
import json
import re
import pyomo.environ as pyo
from random import sample


# Import data
def json_to_pd(data: str) -> (pd.DataFrame, pd.DataFrame):
    """
    :param data: provide json path
    :return:     pd.DataFrame for nodes and channels, as required
    """
    with open(data) as f:
        d = json.load(f)
    nodes, channels = pd.DataFrame(d["nodes"]), pd.DataFrame(d["edges"])
    return nodes, channels


def _filter_dates(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    This method filters out the entries with no update time, thus
    not useful.
    :param pd_object: nodes or channels dataframe to be filtered
    :return: pandas dataframe with filtered rows
    """
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit="s")
    pd_object = pd_object[pd_object.loc[:, "last_update"] > "1970-01-01"]
    return pd_object


# --------------------------------
# Nodes initial dataset cleaning |
# --------------------------------

def _allocate_code(addresses):
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


def _node_addresses(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for nodes
    :return: cleaned pandas dataframe for nodes
    """
    # Ip addresses
    pd_object.loc[:, "addresses"] = pd_object.iloc[:, 3].apply(
        lambda x: [i["addr"] for i in x]
    )
    pd_object.loc[:, "addresses"] = pd_object.loc[:, "addresses"].apply(_allocate_code)

    return pd_object


def nodes_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
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

def _channel_filtering(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for channels
    :return: cleaned pandas dataframe for channels
    """
    pd_object = pd_object[
        pd.notnull(pd_object.loc[:, "node1_policy"]) & pd.notnull(pd_object.loc[:, "node2_policy"])
        ]

    return pd_object


def _fees_extraction(pd_object: pd.DataFrame) -> pd.DataFrame:
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


def _fees_conversion(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: channels dataframe
    :return: channels dataframe with converted fees
    """
    pd_object["fee_base_msat"] = pd_object["fee_base_msat"] / 1000
    pd_object["fee_rate_milli_msat"] = pd_object["fee_rate_milli_msat"] / 1000000
    pd_object.rename(columns={"fee_base_msat": "base_fee", "fee_rate_milli_msat": "rate_fee"}, inplace=True)
    return pd_object


def _channel_data_types(pd_object: pd.DataFrame) -> pd.DataFrame:
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


def channels_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
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

def _nodes_df_splitting(pd_object: pd.DataFrame, n: int) -> list:
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


def _find_channels(n: str, df_channels: pd.DataFrame) -> list:
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
        if df_channels.loc[c, "node1_pub"] == n.name:
            channels_list.append(c)
    return channels_list


def _parallel_channel_finding(args: tuple, pd_object: pd.DataFrame) -> pd.DataFrame:
    dfs, i = args
    df = dfs[i].copy()
    df["outgoing_channels"] = df.apply(_find_channels(pd_object), axis=1)
    return df


def _append_inv_channel(c: list) -> list:
    ris = []
    for i in c:
        ris.append("INV" + str(i))
    return ris


def _flipped_channels(pd_object: pd.DataFrame) -> pd.DataFrame:
    pd_object["incoming_channels"] = pd_object["outgoing_channels"].apply(_append_inv_channel)
    return pd_object


def _drop_not_connected(nodes: pd.DataFrame, channels: pd.DataFrame ) -> pd.DataFrame:
    """
    :param nodes: nodes dataframe
    :param channels: channels dataframe
    :return: filtered nodes dataframe containing only the nodes
     that appear at least once in the channels dataframe
    """
    return nodes[nodes.index.isin(channels["node1_pub"]) or nodes.index.isin(channels["node2_pub"])]


def split_compute_concat(nodes: pd.DataFrame, channels: pd.DataFrame, slices: int) -> pd.DataFrame:
    """
    :param nodes: nodes dataframe before splitting
    :param channels: channels dataframe
    :param slices: number of slices to split the nodes df into
    :return: nodes dataframe with the new columns computed after splitting
    """
    pd_object = _drop_not_connected(nodes, channels)
    dataframes = _nodes_df_splitting(pd_object, slices)

    # Compute in parallel the channel finding and appending of channels list
    pool = Pool()
    inputs: list = [(dataframes, y) for y in range(slices)]
    outputs: list = pool.map(_parallel_channel_finding, inputs)
    pd_object = _flipped_channels(pd.concat(outputs))

    return pd_object


# ------------------------------------------------
# Directed edges creation for channels dataframe |
# ------------------------------------------------























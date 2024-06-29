import random

import pandas as pd
import json
import re
import pyomo.environ as pyo
from random import sample


def _json_to_pd(data: str) -> (pd.DataFrame, pd.DataFrame):
    """
    :param data: provide json path
    :return:     pd.DataFrame for nodes and channels, as required
    """
    with open(data) as f:
        d = json.load(f)
    nodes, channels = pd.DataFrame(d["nodes"]), pd.DataFrame(d["edges"])
    return nodes, channels


def _allocate_code(addresses):
    """
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


def _node_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for nodes
    :return: cleaned pandas dataframe for nodes
    """
    # Timestamp management
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit="s")
    pd_object = pd_object[pd_object.loc[:, "last_update"] > "1970-01-01"]

    # Ip addresses
    pd_object.loc[:, "addresses"] = pd_object.iloc[:, 3].apply(
        lambda x: [i["addr"] for i in x]
    )
    pd_object.loc[:, "addresses"] = pd_object.loc[:, "addresses"].apply(_allocate_code)

    return pd_object.filter(items=["pub_key", "alias", "addresses"])


def _channel_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for channels
    :return: cleaned pandas dataframe for channels
    """
    # Timestamp management
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit="s")
    pd_object = pd_object[pd_object.loc[:, "last_update"] > "1970-01-01"]

    pd_object.loc[:, "capacity"] = pd_object.loc[:, "capacity"].astype(int)

    pd_object = pd_object[
        pd.notnull(pd_object.loc[:, "node1_policy"]) & pd.notnull(pd_object.loc[:, "node2_policy"])
        ]

    return pd_object.filter(
        items=[
            "channel_id",
            "node1_pub",
            "node2_pub",
            "capacity",
            "node1_policy",
            "node2_policy",
        ]
    )


def _channel_features(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: raw dataframe of channels
    :return: new features for dataframe of channels
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
    # Change data type
    pd_object["node1_fee_base_msat"] = pd_object["node1_fee_base_msat"].astype(int)
    pd_object["node2_fee_base_msat"] = pd_object["node2_fee_base_msat"].astype(int)
    pd_object["node1_fee_rate_milli_msat"] = pd_object[
        "node1_fee_rate_milli_msat"
    ].astype(int)
    pd_object["node2_fee_rate_milli_msat"] = pd_object[
        "node2_fee_rate_milli_msat"
    ].astype(int)

    return pd_object.filter(
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


# This function transforms the channels dataframe into a dataframe with the directed
# relationships between peers and keep only the destination fee.
def _channel_directed_edges_creation(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: channels dataframe
    :return: dataframe of channels with directed relationships and features
    """

    # Copy dataframe flip nodes
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

    return pd_object


def _drop_not_connected(nodes: pd.DataFrame, channels: pd.DataFrame ) -> pd.DataFrame:
    """
    :param nodes: nodes dataframe
    :param channels: channels dataframe
    :return: filtered nodes dataframe containing only the nodes
     that appear at least once in the channels dataframe
    """
    return nodes[nodes.index.isin(channels["node1_pub"])]


def fees_conversion(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: channels dataframe
    :return: channels dataframe with converted fees
    """
    pd_object["fee_base_msat"] = pd_object["fee_base_msat"] / 1000
    pd_object["fee_rate_milli_msat"] = pd_object["fee_rate_milli_msat"] / 1000000
    pd_object.rename(columns={"fee_base_msat": "base_fee", "fee_rate_milli_msat": "rate_fee"}, inplace=True)
    return pd_object


def load_and_transform(data: str) -> tuple:
    nodes, channels = _json_to_pd(data)

    channels = _channel_directed_edges_creation(
        _channel_features(
            _channel_cleaning(
                channels
            )
        )
    ).set_index("channel_id")

    nodes = _node_cleaning(nodes).set_index('pub_key')
    channels = fees_conversion(channels)

    return _drop_not_connected(nodes, channels), channels


def create_demand(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: nodes dataframe
    :return: nodes dataset with demand column
    """
    counterparties = sample(pd_object.index.to_list(), 2)
    sender = counterparties[0]
    receiver = counterparties[1]
    random.seed(874631)
    amount = random.randint(a=10000, b=30000)

    print(
        f"Transaction of {amount} sats from {pd_object[pd_object.index == sender]['alias'].item()} to {pd_object[pd_object.index == receiver]['alias'].item()}.")

    pd_object["demand"] = 0
    pd_object.loc[pd_object.index == sender, "demand"] = -amount
    pd_object.loc[pd_object.index == receiver, "demand"] = amount

    return pd_object


class Channel(object):
    def __init__(self, pd_object: pd.DataFrame):
        pass


class Node(object):
    def __init__(self, pd_object: pd.DataFrame):
        pass

import pandas as pd
import json
import re
import pyomo.environ as pyo


def json_to_pd(data: str, obj: str) -> pd.DataFrame:
    """
    :param data: provide json path
    :param obj:  nodes or channels
    :return:     filtered pd.DataFrame for nodes or for channels, as required
    """
    with open(data) as f:
        d = json.load(f)
    # Correct error in name prompting
    if obj == "channels":
        obj = "edges"
    pd_object: pd.DataFrame = pd.DataFrame(d[obj])
    return pd_object


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


def node_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for nodes
    :return: cleaned pandas dataframe for nodes
    """
    # Timestamp management
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit='s')
    pd_object = pd_object[pd_object["last_update"] > "1970-01-01"]

    # Ip addresses
    pd_object['addresses'] = pd_object.iloc[:, 3].apply(lambda x: [i['addr'] for i in x])
    pd_object["addresses"] = pd_object["addresses"].apply(_allocate_code)

    return pd_object.filter(items=["pub_key",
                                   "alias",
                                   "addresses"
                                   ])


def channel_cleaning(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: pandas dataframe for channels
    :return: cleaned pandas dataframe for channels
    """
    # Timestamp management
    pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit='s')
    pd_object = pd_object[pd_object["last_update"] > "1970-01-01"]

    pd_object["capacity"] = pd_object["capacity"].astype(int)

    pd_object = pd_object[pd.notnull(pd_object["node1_policy"]) & pd.notnull(pd_object["node2_policy"])]

    return pd_object.filter(items=['channel_id',
                                   'node1_pub',
                                   'node2_pub',
                                   'capacity',
                                   'node1_policy',
                                   'node2_policy'
                                   ])


def channel_features(pd_object: pd.DataFrame) -> pd.DataFrame:
    """
    :param pd_object: raw dataframe of channels
    :return: new features for dataframe of channels
    """
    # Extract base fee values
    pd_object['node1_fee_base_msat'] = pd_object['node1_policy'].apply(lambda x: x['fee_base_msat'])
    pd_object['node2_fee_base_msat'] = pd_object['node2_policy'].apply(lambda x: x['fee_base_msat'])
    # Extract fee rate values
    pd_object['node1_fee_rate_milli_msat'] = pd_object['node1_policy'].apply(lambda x: x['fee_rate_milli_msat'])
    pd_object['node2_fee_rate_milli_msat'] = pd_object['node2_policy'].apply(lambda x: x['fee_rate_milli_msat'])
    # Change data type
    pd_object["node1_fee_base_msat"] = pd_object["node1_fee_base_msat"].astype(int)
    pd_object["node2_fee_base_msat"] = pd_object["node2_fee_base_msat"].astype(int)
    pd_object["node1_fee_rate_milli_msat"] = pd_object["node1_fee_rate_milli_msat"].astype(int)
    pd_object["node2_fee_rate_milli_msat"] = pd_object["node2_fee_rate_milli_msat"].astype(int)

    return pd_object.filter(items=['channel_id',
                                   'node1_pub',
                                   'node2_pub',
                                   'capacity',
                                   'node1_fee_base_msat',
                                   'node1_fee_rate_milli_msat',
                                   'node2_fee_base_msat',
                                   'node2_fee_rate_milli_msat'
                                   ])


class Channel(object):
    pass


class Node(object):
    pass

import pandas as pd
import json
import re
import pyomo.environ as pyo


def json_to_pd(data: str, obj: str) -> pd.DataFrame:
    """
    :param data: provide json path
    :param obj:  nodes or channels
    :return:     pd.DataFrame for nodes or for channels, as required
    """
    with open(data) as f:
        d = json.load(f)

    # Correct error in name prompting
    if obj == "channels":
        obj = "edges"

    pd_object: pd.DataFrame = pd.DataFrame(d[obj])

    return pd_object


def time_filter(obj: str) -> pd.DataFrame:
    """
    :param obj: nodes or channels
    :return: filtered pd.DataFrame
    """
    nodes["last_update"] = pd.to_datetime(nodes["last_update"], unit='s')
    nodes = nodes[nodes["last_update"] > "1970-01-01"

    return nodes


class Channel(object):
    pass


class Node(object):
    pass

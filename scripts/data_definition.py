import random
from multiprocessing import Pool
import pandas as pd
import json
import re
from random import sample


class HandleData:
    """
    This class should contain all methods and functions that are useful
    for the importing of data, some general cleaning features (time).
    Find channels(?)
    """
    @classmethod
    def load_from_json(cls, path: str, obj: str) -> pd.DataFrame:
        """
        :param path: provide json path
        :param obj:  provide string "nodes" or "edges"
        :return:    pd.DataFrame for obj (nodes or channels), as required
        """
        with open(path) as f:
            d = json.load(f)
        return pd.DataFrame(d[obj])

    @staticmethod
    def filter_dates(pd_object: pd.DataFrame) -> pd.DataFrame:
        """
        This method filters out the entries with no update time, thus
        not useful.
        :param pd_object: nodes or channels dataframe to be filtered
        :return: pandas dataframe with filtered rows
        """
        pd_object["last_update"] = pd.to_datetime(pd_object["last_update"], unit="s")
        pd_object = pd_object[pd_object.loc[:, "last_update"] > "1970-01-01"]
        return pd_object


class HandleNode(HandleData):
    """
    This class should contain methods specific to Node data.
    - node cleaning (allocate code)
    - drop not connected
    """
    @staticmethod
    def __allocate_code(addresses):
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

    def clean_node(self, pd_object: pd.DataFrame) -> pd.DataFrame:
        """
        :param pd_object: pandas dataframe for nodes
        :return: cleaned pandas dataframe for nodes
        """
        # Ip addresses
        pd_object.loc[:, "addresses"] = pd_object.iloc[:, 3].apply(
            lambda x: [i["addr"] for i in x]
        )
        pd_object.loc[:, "addresses"] = pd_object.loc[:, "addresses"].apply(self.__allocate_code)

        return pd_object.filter(items=["pub_key", "alias", "addresses"])

    @staticmethod
    def drop_not_connected(nodes: pd.DataFrame, channels: pd.DataFrame) -> pd.DataFrame:
        """
        :param nodes: nodes dataframe
        :param channels: channels dataframe
        :return: filtered nodes dataframe containing only the nodes
         that appear at least once in the channels dataframe
        """
        df = nodes[nodes.index.isin(channels["node1_pub"])]
        return df


class HandleChannel(HandleData):
    def clean_channel(self):
        pass

    def feature_creation(self):
        pass

    def directed_graph(self):
        pass

    def fees_conversion(self):
        pass

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
    def __init__(self, data):
        self.raw_data = data

    @classmethod
    def load_from_json(cls, path: str, obj: str):
        """
        :param path: provide json path
        :param obj:  provide string "nodes" or "edges"
        :return:    pd.DataFrame for obj (nodes or channels), as required
        """
        with open(path) as f:
            d = json.load(f)
        return cls(pd.DataFrame(d[obj]))

    def filter_dates(self):
        """
        This method filters out the entries with no update time, thus
        not useful.
        :param pd_object: nodes or channels dataframe to be filtered
        :return: pandas dataframe with filtered rows
        """
        self.raw_data["last_update"] = pd.to_datetime(self.raw_data["last_update"], unit="s")
        pd_object = self.raw_data[self.raw_data.loc[:, "last_update"] > "1970-01-01"]
        self.raw_data = pd_object
        return self.raw_data

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

    def clean_node(self):
        """
        :param pd_object: pandas dataframe for nodes
        :return: cleaned pandas dataframe for nodes
        """
        # Ip addresses
        self.raw_data.loc[:, "addresses"] = self.raw_data.iloc[:, 3].apply(
            lambda x: [i["addr"] for i in x]
        )
        self.raw_data.loc[:, "addresses"] = self.raw_data.loc[:, "addresses"].apply(self.__allocate_code)
        self.raw_data = self.raw_data.filter(items=["pub_key", "alias", "addresses"])

        return self.raw_data


class HandleChannel(HandleData):
    @staticmethod
    def clean_channel(pd_object: pd.DataFrame) -> pd.DataFrame:
        """
        :param pd_object: pandas dataframe for channels
        :return: cleaned pandas dataframe for channels
        """
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

    @staticmethod
    def feature_creation(pd_object: pd.DataFrame) -> pd.DataFrame:
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

    @staticmethod
    def directed_graph(pd_object: pd.DataFrame) -> pd.DataFrame:
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
            items=["channel_id", "node1_pub", "node2_pub", "capacity", "node2_fee_base_msat",
                   "node2_fee_rate_milli_msat"])
        pd_object.rename(
            columns={"node2_fee_base_msat": "fee_base_msat", "node2_fee_rate_milli_msat": "fee_rate_milli_msat"},
            inplace=True)

        return pd_object

    @staticmethod
    def fees_conversion(pd_object: pd.DataFrame) -> pd.DataFrame:
        """
        :param pd_object: channels dataframe
        :return: channels dataframe with converted fees
        """
        pd_object["fee_base_msat"] = pd_object["fee_base_msat"] / 1000
        pd_object["fee_rate_milli_msat"] = pd_object["fee_rate_milli_msat"] / 1000000
        pd_object.rename(columns={"fee_base_msat": "base_fee", "fee_rate_milli_msat": "rate_fee"}, inplace=True)
        return pd_object

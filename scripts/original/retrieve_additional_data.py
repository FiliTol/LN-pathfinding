import requests
import pandas as pd
import time
from tqdm import tqdm


data_folder = "data/original/"
nodes = pd.read_csv(f"{data_folder}nodes.csv")


def retrieve_node_data(key: str) -> dict:
    """
    Function that retrieves a node data with the LN+ API
    :param key: node public key
    :return: dict containing node data
    """
    try:
        request = requests.get(f"https://lightningnetwork.plus/api/2/get_node/pubkey={key}")
        request.raise_for_status()
        dict_data = request.json()
        dict_data.pop("profile_urls", None)

        time.sleep(0.5)

        return dict_data

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred: {req_err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return {}


def additional_features_df(nodes: pd.DataFrame, rg_start: int = 1, rg_end: int = -1) -> pd.DataFrame:
    """
    Function that creates the dataframe of additional features to be assigned to each vertex (node)
    :param nodes: dataframe of nodes. Used to retrieve pubkey in the index range
    :param rg_start: start index so search through in the nodes dataframe
    :param rg_end: end index so search through in the nodes dataframe
    :return: final dataframe containing additional features for each pubkey
    """
    try:
        df_list = []
        pubkeys = nodes.loc[rg_start:rg_end, "pub_key"].to_list()
        for k in tqdm(pubkeys):
            node_data = retrieve_node_data(k)
            df_list.append(node_data)
        df = pd.DataFrame.from_dict(df_list, orient='columns')
        df.to_csv(f"{data_folder}additional_features_{rg_start}_{rg_end}.csv")
        return print(f"Data retrieval session completed ({rg_start}-{rg_end})")
    except:
        print("Something went wrong")


additional_features_df(nodes=nodes, rg_start=3601, rg_end=11983)

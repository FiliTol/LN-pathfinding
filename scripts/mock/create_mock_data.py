import json
import random
import string


def generate_random_string(length):
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


def generate_node(pub_key):
    node = {
        "last_update": 1720108241,
        "pub_key": pub_key,
        "alias": pub_key + ".com",
        "addresses": [
            {"network": "tcp", "addr": generate_random_string(20) + ".onion:9735"}
        ],
        "color": "#" + "".join(random.choices("0123456789abcdef", k=6)),
        "features": {
            "0": {
                "name": "data-loss-protect",
                "is_required": random.choice([True, False]),
                "is_known": random.choice([True, False]),
            }
        },
        "custom_records": {},
    }
    return node


def generate_edge(channel_id, node1_pub, node2_pub):
    edge = {
        "channel_id": channel_id,
        "chan_point": generate_random_string(10) + ":1",
        "last_update": 1720108241,
        "node1_pub": node1_pub,
        "node2_pub": node2_pub,
        "capacity": str(random.randint(100000, 9999999)),
        "node1_policy": {
            "time_lock_delta": random.randint(50, 100),
            "min_htlc": str(random.randint(100, 1000)),
            "fee_base_msat": str(random.randint(0, 1000)),
            "fee_rate_milli_msat": str(random.randint(0, 10)),
            "disabled": random.choice([True, False]),
            "max_htlc_msat": str(random.randint(1000000, 9999999)),
            "last_update": 1720108241,
            "custom_records": {},
        },
        "node2_policy": {
            "time_lock_delta": random.randint(50, 100),
            "min_htlc": str(random.randint(100, 1000)),
            "fee_base_msat": str(random.randint(0, 1000)),
            "fee_rate_milli_msat": str(random.randint(0, 10)),
            "disabled": random.choice([True, False]),
            "max_htlc_msat": str(random.randint(1000000, 9999999)),
            "last_update": 1720108241,
            "custom_records": {},
        },
        "custom_records": {},
    }
    return edge


nodes = []
edges = []
list_pub_key = []

for i in range(100):
    pub_key = "".join(random.choices("ABCDEFGHILMNOPQRSTUVZ", k=10))
    list_pub_key.append(pub_key)
    nodes.append(generate_node(pub_key))

for i in range(350):
    channel_id = "".join(random.choices(string.digits, k=18))
    ris = random.sample(list_pub_key, k=2)
    node1_pub = ris[0]
    node2_pub = ris[1]
    # node1_pub = ''.join(random.choices('0123456789abcdef', k=66))
    # node2_pub = ''.join(random.choices('0123456789abcdef', k=66))
    edges.append(generate_edge(channel_id, node1_pub, node2_pub))

data = {"nodes": nodes, "edges": edges}

with open("data/mock/mock_dataset.json", "w") as file:
    json.dump(data, file, indent=4)

print("Mock dataset generated and saved to mock_dataset.json")
print(list_pub_key)

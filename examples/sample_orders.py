import json


def load_orders(path):
    with open(path) as f:
        return json.load(f)


def total_revenue(orders):
    ...


def summarize(order):
    # TODO: return the customer name and total as a dict
    ...

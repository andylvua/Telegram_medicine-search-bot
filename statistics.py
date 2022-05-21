import pandas as pd
from pymongo import MongoClient

import configparser
import json

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import seaborn as sns

from regex_engine import generator

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config['Database']['cluster'])
db = cluster.TestBotDatabase
collection = db.TestBotCollection


def get_quantities(path: str) -> dict:
    """
    The get_quantities function takes a path to a json file containing country codes and returns
    a dictionary with the quantities of countries that match the regex for each code.

    :param path: Specify the path to the json file containing the country codes
    :return: A dictionary with the country codes as keys and the number of documents that match each code as values
    """
    with open(path) as json_file:
        country_codes = json.load(json_file)
    
    quantities = dict()
    generate = generator()
    
    for key, value in country_codes.items():
        key_splitted = key.split("–")
    
        if len(key_splitted) == 2:
            key_pair = (int(key_splitted[0]), int(key_splitted[1]))
            regex = generate.numerical_range(key_pair[0], key_pair[1]).strip("$")
            quantity = collection.count_documents({"code": {'$regex': f'{regex}'}})
        else:
            int_key = int(key)
            quantity = collection.count_documents({"code": {'$regex': f'^{int_key}'}})
    
        quantities[value] = int(quantity)

    return quantities
    

def get_not_empty_countries(quantities: dict) -> dict:
    """
    The get_not_empty_countries function takes a dictionary of country names and quantities as input.
    It returns a new dictionary containing only the countries that have at least one quantity greater than zero.

    :param quantities: Store the quantities of each country
    :return: A dictionary of countries that have values greater than 0 in the quantities dictionary
    """
    countries = dict()

    for key, value in quantities.items():
        if value != 0:
            countries[key] = value
        else:
            continue
    
    return countries


def get_bar_chart(countries: dict) -> plt.figure:
    """
    The get_bar_chart function creates a bar chart of the countries and their respective quantities.
    It takes in a dictionary as an argument, which is then converted into a pandas dataframe. The dataframe
    is sorted by quantity, descending order, and then plotted using seaborn.

    :param countries: Pass a dictionary of countries and their respective number of msb's
    :return: A matplotlib.pyplot.figure bar chart of the countries and their respective quantity
    """
    df = pd.DataFrame(countries.items(), columns=['Country', 'Quantity'])
    df.sort_values(by='Quantity', ignore_index=True, ascending=False, inplace=True)

    plot = plt.figure(figsize=(15, 10))

    sns.barplot(
        x="Country",
        y="Quantity",
        data=df,
        estimator=sum,
        ci=None,
        color='#8c0f24'
    )

    plt.gca().set_title('MSB Statistics', fontsize=20, fontweight='bold')
    plt.gca().yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.xticks(fontsize=14)
    plt.xlabel("Country", fontsize=14, fontweight='bold', labelpad=20)
    plt.yticks(fontsize=14)
    plt.ylabel("Quantity", fontsize=14, fontweight='bold', labelpad=20)

    plt.gca().bar_label(plt.gca().containers[0], fontsize=14, fontweight='bold',
                        label_type='center', color='white')

    return plot

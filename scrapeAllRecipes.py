import requests
import csv
from bs4 import BeautifulSoup
import re   
import spacy
import urllib.parse
import json
from difflib import SequenceMatcher
import psycopg2
from config import config

def cleanName(name, nlp):
    removalWords = ["diced","sliced","divided","drained","rinsed","finely","split","beaten","chopped","to taste"]

    doc = nlp(name)
    nounList = list(doc.noun_chunks)
    if len(nounList) == 1:
        return nounList[0].text

    elif len(nounList) > 1:
        for removalWord in removalWords:
            # name = name.replace(removalWord, "")
            rawString = r"{}".format(removalWord)
            name = re.sub(rawString,"",name,flags=re.IGNORECASE)
        name.replace(",","")
        doc = nlp(name)
        nounList = list(doc.noun_chunks)
        if len(nounList) == 1:
            return nounList[0].text
        else:
            return name      
        
    else:            
        for removalWord in removalWords:
            # name = name.replace(removalWord, "")
            rawString = r"{}".format(removalWord)
            name = re.sub(rawString,"",name,flags=re.IGNORECASE)
        name.replace(",","")
        name.strip()
        return name

def connect():    
    dbParams = config()
    conn = psycopg2.connect(**dbParams)
    cursor = conn.cursor()
    return cursor

def getIngredientDB(name):
    cursor = connect()
    cursor.execute("SELECT id, ingredient_name, api_id, api_name FROM ingredient WHERE ingredient_name LIKE '" + name + "'")

    records = cursor.fetchall()
    returnList = []
    returnDict = {}

    for record in records:
        returnDict = {
            "ID":record[0],
            "Name":record[1],
            "APIID":record[2],
            "APIName":record[3]
        }
        returnList.append(returnDict)

    return returnList

def getIngredientDetailAPI(name):
    urlEncodedName = urllib.parse.quote(name)
    ingredientAPIURL = spoonacularBaseURL + "/food/ingredients/search?apiKey=" + spoonacularAPIKey + "&query=" + urlEncodedName
    ingredientResponse = requests.get(ingredientAPIURL)
    ingredientResponseObj = json.loads(ingredientResponse.text)
    return ingredientResponseObj

nlp = spacy.load("en_core_web_sm")
url = "https://www.allrecipes.com/recipe/92462/slow-cooker-texas-pulled-pork/"
# url = "https://www.allrecipes.com/recipe/14656/meatloaf-with-fried-onions-and-ranch-seasoning/"
# url = "https://www.allrecipes.com/recipe/230679/jessicas-red-beans-and-rice/"
# url = "https://www.allrecipes.com/recipe/70343/slow-cooker-chicken-taco-soup/"

spoonacularConfig = config(section="spoonacular")
spoonacularAPIKey = spoonacularConfig["apikey"]
spoonacularBaseURL = spoonacularConfig["baseurl"]

print(url)

# Get recipe HTML
response = requests.get(url)
html = response.text
soup = BeautifulSoup(html, "html.parser")

# Get list of ingredients
ingredientListContainer = soup.find("ul",attrs={"class": "mntl-structured-ingredients__list"})
ingredientList = ingredientListContainer.find_all("li")
csvList = []

# For each ingredient...
for ingredient in ingredientList: 

    # Get all parts of the ingredient item (quantity, unit and name)
    ingredientParts = ingredient.find_all("span")
    dictionary = {}

    # For each ingredient part...
    for part in ingredientParts:
        keys = []

        # Create a list of element attributes 
        for key in part.attrs.keys():
           keys.append(key)      

        # If it's a quantity part add it to the dict
        if keys.count("data-ingredient-quantity") > 0:
            dictionary["quantity"] = part.text

        # If it's a unit part add it to the dict
        if keys.count("data-ingredient-unit") > 0:
            dictionary["unit"] = part.text
        
        # If it's a name part add it to the dict
        if keys.count("data-ingredient-name") > 0:
            name = part.text.lower()
            dictionary["name"] = name
            dbResult = getIngredientDB(name)

            if len(dbResult) > 0:
                returnResult = {
                    "id": dbResult[0]["APIID"],
                    "name": dbResult[0]["APIName"]
                    }
            else:
                cleanedName = cleanName(name, nlp)
                dbResult = getIngredientDB(cleanedName)

                if len(dbResult) > 0:
                    returnResult = {
                        "id": dbResult[0]["APIID"],
                        "name": dbResult[0]["APIName"]
                        }
                else:
                    ingredientResponseObj = getIngredientDetailAPI(name)

                    if len(ingredientResponseObj["results"]) > 1:
                        previousHighestRatio = 0
                        returnResult = {}
                        for result in ingredientResponseObj["results"]:
                            ratio = SequenceMatcher(None, name, result["name"]).ratio()
                            # print("Ratio: " + str(ratio) + ", Name: " + result["name"])
                            if ratio > previousHighestRatio:
                                previousHighestRatio = ratio
                                returnResult = result

                    elif len(ingredientResponseObj["results"]) == 1:
                        returnResult = ingredientResponseObj["results"][0]
                    else:
                        cleanedName = cleanName(name, nlp)
                        ingredientResponseObj = getIngredientDetailAPI(cleanedName)

                        if len(ingredientResponseObj["results"]) > 1:
                            previousHighestRatio = 0
                            returnResult = {}
                            for result in ingredientResponseObj["results"]:
                                ratio = SequenceMatcher(None, cleanedName, result["name"]).ratio()
                                # print("Ratio: " + str(ratio) + ", Name: " + result["name"])
                                if ratio > previousHighestRatio:
                                    previousHighestRatio = ratio
                                    returnResult = result

                        elif len(ingredientResponseObj["results"]) == 1:
                            returnResult = ingredientResponseObj["results"][0]
                        else:
                            if "seasoning" in cleanedName:
                                dbResult = getIngredientDB("seasoning")
                                if len(dbResult) > 0:
                                    returnResult = {
                                        "id": dbResult[0]["APIID"],
                                        "name": dbResult[0]["APIName"]
                                        }
                                else:
                                    ingredientResponseObj = getIngredientDetailAPI("seasoning mix")

                                    if len(ingredientResponseObj["results"]) > 1:
                                        returnResult = [result for result in ingredientResponseObj["results"] if result['name'] == "seasoning mix"][0]
                                    elif len(ingredientResponseObj["results"]) == 1:
                                        returnResult = ingredientResponseObj["results"][0]
                                    else:
                                        print("Error - no matching ingredient")
                                    
                            else:
                                print("Error - no matching ingredient")
                dictionary["apiID"] = returnResult["id"]
                dictionary["apiName"] = returnResult["name"]

    csvList.append(dictionary)

with open("C:/temp/scrapeAllRecipesResults.csv", "w", newline="\n", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, dictionary.keys(), dialect="excel-tab")
    w.writeheader()
    w.writerows(csvList)
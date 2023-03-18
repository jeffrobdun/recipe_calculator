import requests
from unicodedata import numeric
from bs4 import BeautifulSoup
import re   
import spacy
import urllib.parse
import json
from difflib import SequenceMatcher
import psycopg2
from psycopg2.extras import execute_values
from config import config

def cleanName(name, nlp):
    removalWords = ["diced","sliced","divided","drained","rinsed","finely","split","beaten","chopped","to taste","halved","quartered","large","small","medium"]

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
    return conn

def getIngredientDB(name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * from public.get_ingredient_by_name('" + name + "')")

    records = cursor.fetchall()
    conn.close()
    
    returnList = []
    returnDict = {}

    for record in records:
        returnDict = {
            "id":record[0],
            "name":record[1],
            "api_id":record[2],
            "api_name":record[3],
            "possible_units":json.dumps(record[4])
        }
        returnList.append(returnDict)
    
    return returnList

def getIngredientAPI(name):
    urlEncodedName = urllib.parse.quote(name)
    ingredientAPIURL = spoonacularBaseURL + "/food/ingredients/search?apiKey=" + spoonacularAPIKey + "&query=" + urlEncodedName
    ingredientResponse = requests.get(ingredientAPIURL)
    ingredientResponseObj = json.loads(ingredientResponse.text)
    return ingredientResponseObj

def getIngredientDetailAPI(id):
    ingredientAPIURL = spoonacularBaseURL + "/food/ingredients/" + str(id) + "/information?apiKey=" + spoonacularAPIKey
    ingredientResponse = requests.get(ingredientAPIURL)
    ingredientResponseObj = json.loads(ingredientResponse.text)
    return ingredientResponseObj

def insertIntoLoadData(dictList):
    conn = connect()
    cursor = conn.cursor()
    columns = dictList[0].keys()
    query = "INSERT INTO load_data ({}) VALUES %s".format(','.join(columns))

    values = [[value for value in dict.values()] for dict in dictList]
    execute_values(cursor, query, values)
    conn.commit()
    conn.close()

def parseLoadData():
    conn = connect()
    cursor = conn.cursor()
    query = "SELECT * FROM parse_loaded_data()"
    cursor.execute(query)
    conn.commit()
    records = cursor.fetchall()
    conn.close()
    if(records[0][0] == 1):
        return True
    else:
        return False

def getCleanUnits(possibleUnits, unit, nlp=None):
    removalWords = ["diced","sliced","divided","drained","rinsed","finely","split","beaten","chopped","to taste","halved","quartered","large","small","medium"]

    unit.replace("(","")
    unit.replace(")","")
    possibleUnits = json.loads(possibleUnits)
    returnResults = []
    # print("***************************************")
    # print("Unit: " + unit)
    if "oz" in possibleUnits:
        possibleUnits.append("ounce")

    if "g" in possibleUnits:
        possibleUnits.append("gram")

    for removalWord in removalWords:
        # name = name.replace(removalWord, "")
        removalString = r"{}".format(removalWord)
        unit = re.sub(removalString,"",unit,flags=re.IGNORECASE)
        
    for possibleUnit in possibleUnits:
        # print("possibleUnit: " + possibleUnit)
        rawString = r"[0-9]* *{}".format(possibleUnit)
        # print("rawString: " + rawString)
        results = re.findall(rawString, unit)
        returnResults = results + returnResults
        # print("results: " + json.dumps(results))

    # print(returnResults)
    # print("***************************************")
    
    return returnResults

def fractionsToDecimals(fraction):
    if len(fraction) == 1:
        decimal = numeric(fraction)
    elif fraction[-1].isdigit():
        decimal = float(fraction)
    else:
        decimal = float(fraction[:-1]) + numeric(fraction[-1])
    return decimal

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
insertList = []

# For each ingredient...
for ingredient in ingredientList: 

    # Get all parts of the ingredient item (quantity, unit and name)
    ingredientParts = ingredient.find_all("span")
    dictionary = {}
    dictionary['recipe_url'] = url

    # For each ingredient part...
    for part in ingredientParts:
        keys = []

        # Create a list of element attributes 
        for key in part.attrs.keys():
           keys.append(key)      

        # If it's a quantity part add it to the dict
        if keys.count("data-ingredient-quantity") > 0:
            dictionary["quantity"] = fractionsToDecimals(part.text)

        # If it's a unit part add it to the dict
        if keys.count("data-ingredient-unit") > 0:
            dictionary["unit"] = part.text
        
        # If it's a name part add it to the dict
        if keys.count("data-ingredient-name") > 0:
            name = part.text.lower()
            dictionary["name"] = name

            # Try to pull the ingredient from the database
            dbResult = getIngredientDB(name)

            # If a result is returned from the DB...
            if len(dbResult) > 0:
                returnResult = {
                        "api_id": dbResult[0]["api_id"],
                        "api_name": dbResult[0]["api_name"],
                        "possible_units":dbResult[0]["possible_units"]
                    }
            else:
                # Clean the name so it is just the ingredient
                cleanedName = cleanName(name, nlp)

                # Try to pull the ingredient from the database
                dbResult = getIngredientDB(cleanedName)

                # If a result is returned from the DB...
                if len(dbResult) > 0:
                    returnResult = {
                            "api_id": dbResult[0]["api_id"],
                            "api_name": dbResult[0]["api_name"],
                            "possible_units":dbResult[0]["possible_units"]
                        }
                else:
                    # Try to get the ingredient from the API
                    ingredientResponseObj = getIngredientAPI(name)
                    print(ingredientResponseObj)

                    # If more than one result was returned from the API
                    if len(ingredientResponseObj["results"]) > 1:
                        previousHighestRatio = 0
                        returnResult = {}

                        # Get the most relevant result by name
                        for result in ingredientResponseObj["results"]:
                            ratio = SequenceMatcher(None, name, result["name"]).ratio()
                            if ratio > previousHighestRatio:
                                previousHighestRatio = ratio
                                returnResult = {
                                    "api_name": result["name"],
                                    "api_id": result["id"]
                                }

                    elif len(ingredientResponseObj["results"]) == 1:
                        result = ingredientResponseObj["results"][0]
                        returnResult = {
                                        "api_name": result["name"],
                                        "api_id": result["id"]
                                    }
                    else:
                        cleanedName = cleanName(name, nlp)
                        ingredientResponseObj = getIngredientAPI(cleanedName)

                        if len(ingredientResponseObj["results"]) > 1:
                            previousHighestRatio = 0
                            returnResult = {}
                            for result in ingredientResponseObj["results"]:
                                ratio = SequenceMatcher(None, cleanedName, result["name"]).ratio()

                                if ratio > previousHighestRatio:
                                    previousHighestRatio = ratio
                                    returnResult = {
                                        "api_name": result["name"],
                                        "api_id": result["id"]
                                    }

                        elif len(ingredientResponseObj["results"]) == 1:
                            returnResult = ingredientResponseObj["results"][0]
                        else:
                            if "seasoning" in cleanedName:
                                dbResult = getIngredientDB("seasoning")
                                if len(dbResult) > 0:
                                    returnResult = {
                                        "api_id": dbResult[0]["api_id"],
                                        "api_name": dbResult[0]["api_name"],
                                        "possible_units":dbResult[0]["possible_units"]
                                    }
                                else:
                                    ingredientResponseObj = getIngredientAPI("seasoning mix")

                                    if len(ingredientResponseObj["results"]) > 1:
                                        foundResult = [result for result in ingredientResponseObj["results"] if result['name'] == "seasoning mix"][0]
                                        returnResult = {
                                            "api_name": foundResult["name"],
                                            "api_id": foundResult["id"]
                                        }
                                    elif len(ingredientResponseObj["results"]) == 1:
                                        returnResult = ingredientResponseObj["results"][0]
                                    else:
                                        print("Error - no matching ingredient")
                                    
                            else:
                                print("Error - no matching ingredient")

                    if "possible_units" not in returnResult.keys() or returnResult["possible_units"] == None:
                        print(returnResult["api_id"])
                        ingredientDetails = getIngredientDetailAPI(returnResult["api_id"])
                        returnResult["possible_units"] = json.dumps(ingredientDetails['possibleUnits'])

            dictionary["api_id"] = returnResult["api_id"]
            dictionary["api_name"] = returnResult["api_name"]
            
            dictionary["possible_units"] = returnResult["possible_units"]
            actualUnits = []
            if dictionary["unit"] != None and dictionary["unit"] != "":
                actualUnits = getCleanUnits(returnResult["possible_units"], dictionary["unit"])
            
            dictionary["actual_units"] = json.dumps(actualUnits)

    insertList.append(dictionary)

insertIntoLoadData(insertList)
parseDataSuccess = parseLoadData()
if not parseDataSuccess:
    print("Error - could not parse loaded data")
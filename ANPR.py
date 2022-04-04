import math
import sqlite3
import cv2
import requests
import base64
import json
import os
from bs4 import BeautifulSoup
from urllib.request import urlopen

def create_database():
    """ Creates a database and creates a table within it. """
    conn = sqlite3.connect('license_plates.db')
    cur = conn.cursor()

    cur.execute(""" SELECT count(name) FROM sqlite_master WHERE type='table'
                AND name='plates' """)

    if cur.fetchone()[0] != 1:
        cur.execute("""CREATE TABLE plates (
                     license_plate text,
                     plate_confidence real,
                     time real
                     )""")
        print("Successfully created database!")

    conn.commit()
    conn.close()

def extract_frames():
    """ Extracts frames from a video and saves to a directory. """
    video = "nz_cars_ALPR.mp4"
    save_directory = ""
    cap = cv2.VideoCapture(video)
    frame_rate = cap.get((cv2.CAP_PROP_FPS))
    count = 0
    while cap.isOpened():
        frame_identifier = cap.get(1)
        res, frame = cap.read()
        if res != True:
            break
        if frame_identifier % math.floor(frame_rate) == 0:
            filename = save_directory + str(count) + ".jpg"
            cv2.imwrite(filename, frame)
            count += 1
    cap.release()
    print(f"Successfully extracted {} frames!")

def check_thatcar(plate):
    """ Enters the plate into thatcar.nz and scrapes make, model and colour. """
    url = f"https://thatcar.nz/c/?q={plate}"
    page = urlopen(url)
    html = page.read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    data = []
    table = soup.find('table', attrs={'class':'table'})
    rows = table.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        cols = [i.text.strip() for i in cols]
        data.append([i for i in cols if i])
    make = str(rows[1])
    model = str(rows[2])
    colour = str(rows[5])

    make = make.split()
    make = make[3].lower()

    model = model.split()
    model = model[3].lower()

    colour_list = colour.split()
    colour = "UNKNOWN" #For if the website does not have the colour of the vehicle
    for i in colour_list:
        if "Colour" in i:
            colour = colour_list[2].replace("<td>", "").replace("</td>", "").lower()

    return make, model, colour

def process_images():
    """ Iterates through all images in directory, sends data to OpenALPR and saves data to 'plates' database """
    directory = os.path.abspath(os.path.dirname(__file__))
    result = []
    for filename in os.listdir(directory):
        if filename.endswith(".jpg"):
            IMAGE_PATH = filename
            SECRET_KEY = "sk_65527a6200e31fc7bbace328"

            with open(IMAGE_PATH, 'rb') as image_file:
                img_base64 = base64.b64encode(image_file.read())
            url = "https://api.openalpr.com/v3/recognize_bytes?recognize_vehicle=1&country=eu&secret_key=%s" % (SECRET_KEY)
            data = requests.post(url, data = img_base64)
            json_data = data.json()

            conn = sqlite3.connect('license_plates.db')
            cur = conn.cursor()

            if json_data["results"]:
                prediction = json_data["results"][0]["plate"]
                confidence = json_data["results"][0]["confidence"]
                processing_time = json_data["processing_time"]["plates"]

                make = json_data["results"][0]["vehicle"]["make"][0]["name"]
                make_confidence = json_data["results"][0]["vehicle"]["make"][0]["confidence"]
        
                make_model = json_data["results"][0]["vehicle"]["make_model"][0]["name"].split("_")
                model = make_model[1]
                model_confidence = json_data["results"][0]["vehicle"]["make_model"][0]["confidence"]
        
                colour = json_data["results"][0]["vehicle"]["color"][0]["name"]
                colour_confidence = json_data["results"][0]["vehicle"]["color"][0]["confidence"]

                cur.execute(f"SELECT EXISTS(SELECT 1 FROM plates WHERE license_plate='{prediction}')") #Checks whether the plate is already in the database, to prevent duplicate frame data
                
                if cur.fetchone()[0] != 1:
                    instruction = f"INSERT INTO plates VALUES ('{prediction}', {confidence}, {processing_time})"
                    cur.execute(instruction)

                website_make, website_model, website_colour = check_thatcar(prediction)

                make_result = (website_make == make)
                model_result = (website_model == model)
                if colour != "UNKNOWN":
                    colour_result = (website_colour == colour)
                else:
                    colour_result = "UNKNOWN"

                result.append(f"Image: {filename}\nplate: {prediction} confidence: {confidence} processing time: {processing_time}\n"
                              f"make: {make} confidence: {make_confidence}\nmodel: {model} confidence: {model_confidence}\n"
                              f"colour: {colour} confidence: {colour_confidence}\n"
                              f"Details vs thatcar.nz: make: {make_result} model: {model_result} colour: {colour_result}\n"
                              )
            conn.commit()
            conn.close()

            
            else:
                print(f"OpenALPR could not identify a license plate within {filename}\n")

    for i in result:
        print(i)
    
    
def main():
    create_database()
    extract_frames()
    process_images()

main()

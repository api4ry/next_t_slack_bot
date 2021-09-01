# next_t.py
# Enable info level logging
import logging
logging.basicConfig(level=logging.INFO)

import os
from slack_sdk.webhook import WebhookClient
from dotenv import load_dotenv
from flask import Flask, request, make_response
from threading import Thread
import requests
import json

#load secrets / config
load_dotenv()

#Webhook requests from Slack to the bot will be signed
from slack_sdk.signature import SignatureVerifier
signature_verifier = SignatureVerifier(
    signing_secret=os.environ['SLACK_SIGNING_SECRET']
)

#flask to respond to interaction requests from Slack
app = Flask(__name__)


@ app.route('/slash_command', methods=['POST'])
def slash_command():
    #signature checking conditional from the slack api docs.https://slack.dev/python-slack-sdk/webhook/index.html#id1
    if not signature_verifier.is_valid(
            body=request.get_data(),
            timestamp=request.headers.get('X-Slack-Request-Timestamp'),
            signature=request.headers.get('X-Slack-Signature')):
        return make_response('invalid request', 403)

    data = request.form
    #user provides a location to the slash command to get the time when the next T departs near them.
    location = data.get('text')
    #Request to HERE to fetch geocoded location for the stop.
    hereParams = {'q': location, 'apiKey': os.environ['HEREKEY']}
    r = requests.get('https://geocode.search.hereapi.com/v1/geocode', params= hereParams)

    if r.status_code == 200:
        geocode = json.loads(r.text)
        address = geocode['items'][0]['title']
        lat = geocode['items'][0]['position']['lat']
        lng = geocode['items'][0]['position']['lng']
    else:
        return 'There was an error looking up stop information.'

    #start a thread to check the next train and return the data using the provided response URL.
    Thread(target= checkNextTrain, args=(data.get('response_url'), lat, lng)).start()

    #The slash command API needs a response, even a blank one, within 3 seconds.
    return 'Looking up next arrival at closest stop to ' + address






@ app.route('/buttons', methods=['POST'])
def buttons():
    # signature checking conditional from the slack api docs.https://slack.dev/python-slack-sdk/webhook/index.html#id1
    if not signature_verifier.is_valid(
            body=request.get_data(),
            timestamp=request.headers.get('X-Slack-Request-Timestamp'),
            signature=request.headers.get('X-Slack-Signature')):
        return make_response('invalid request', 403)

    data = request.form['payload']
    #Slack uses blocks for message composition.
    requestBlock = json.loads(data)

    requestSession = requests.Session()
    requestSession.headers.update({'x-api-key': os.environ['MBTAKEY'], 'accept': 'application/vnd.api+json'})
    #The button value contains the routeId and stopId associated with the selected stop
    (routeId, stopId)= requestBlock['actions'][0]['value'].split(',')

    paramMbta = {'filter[stop]': stopId, 'filter[route]': routeId, 'include': 'stop,route','sort': 'departure_time'}
    r = requestSession.get('https://api-v3.mbta.com/predictions', params= paramMbta)
    predictions = json.loads(r.text)

    #send a request to the provided response url with the next predictions for the requested stop
    webhook = WebhookClient(requestBlock['response_url'])
    webhook.send(text=getFormattedPrediction(predictions, requestBlock['actions'][0]['text']['text']))

    #returning a blank 200 OK response, the prediction was sent to the response URL.
    return ''


#called asynchronously from slash_command. The respURL is provided in the request from Slack and can be used
#to provide a response to the command for 30 minutes after the original request.
def checkNextTrain(respURL, lat, lng):
    webhook = WebhookClient(respURL)

    s1 = requests.Session()
    s1.headers.update({'x-api-key': os.environ['MBTAKEY'], 'accept': 'application/vnd.api+json'})
    paramMbta = {'filter[latitude]': lat, 'filter[longitude]': lng, 'include': 'stop,route', 'sort': 'departure_time'}
    r = s1.get('https://api-v3.mbta.com/predictions', params= paramMbta)

    predictionData = json.loads(r.text)
    validDepartures = []
    routes = set()
    if (r.status_code == 200):
        #if no valid predictions are found, index will remain at -1
        index = -1
        for x in range(len(predictionData['data'])):
            if predictionData['data'][x]['attributes']['schedule_relationship'] != 'SKIPPED':
                if predictionData['data'][x]['attributes']['departure_time'] != None:
                    #creating list of departures pruned of any null departure times
                    validDepartures.append(predictionData['data'][x])
                    #the same route might have multiple departures,
                    # using a set to get a list of unique route / stop combos
                    routeId = predictionData['data'][index]['relationships']['route']['data']['id']
                    stopId = predictionData['data'][index]['relationships']['stop']['data']['id']
                    stopName = getStopName(predictionData, stopId)
                    routes.add((routeId,stopId,stopName))
                    index = x
                    #For a busy part of town there could be a large number of potential departures, only checking
                    #the first 10
                    if len(validDepartures) > 10:
                        break

        #If index isn't > 0 no valid predictions were found.
        if index == -1:
            webhook.send(text= 'No scheduled MBTA departure was found near you')
            return

        # The response to this choice will come back as a POST request to /buttons.
        webhook.send(blocks= getStopButtons(routes, respURL))
        return

    #Error message sent when the MBTA API returns anything other than a 200 OK.
    else:
        respBody = 'There was an error looking up departure information.'

    #Only errors get this far.
    webhook.send(text = respBody)
    return


def getStopButtons(validStops, respURL):

    button = '{"type": "button","text": {"type": "plain_text","text": ""},"value":""}'
    buttonBlock = [{"type": "section","text": {"type": "mrkdwn","text": "Which stop would you like times for?"}},
              {"type": "actions","block_id": "stop choice","elements": []}]
    buttonList = []
    for routeId, stopId, stopName in validStops:
        temp = json.loads(button)
        temp['text']['text'] = routeId + ' ' + stopName
        temp['value'] = routeId + ',' + stopId
        buttonList.append(temp.copy())
    buttonBlock[1]['elements'] = buttonList

    return buttonBlock



#the included list in the JSON blob is not ordered, it includes stop and route objects,
# these utility functions are to fetch the appropriate objects for the selected prediction
def getStopInfo(stopsData, stopId):
    for x in range(len(stopsData['included'])):
        item = stopsData['included'][x]
        if item['type'] == 'stop':
            if item['id'] == stopId:
                return item
    return None

def getStopName(stopsData, stopId):
    for x in range(len(stopsData['included'])):
        item = stopsData['included'][x]
        if item['type'] == 'stop':
            if item['id'] == stopId:
                return item['attributes']['name']
    return None

def getRouteInfo(stopsData, routeId):
    for x in range(len(stopsData['included'])):
        item = stopsData['included'][x]
        if item['type'] == 'route':
            if item['id'] == routeId:
                return item
    return None

def getFormattedPrediction(predictions, stopName):
    for pred in predictions['data']:
        #The API can return many predictions for a given stop and route combination.
        #The predictions with null departure times are first,
        # and need to be skipped before we get to the first departure.
        if pred['attributes']['departure_time'] != None:
            departureTime = pred['attributes']['departure_time']
            routeId = pred['relationships']['route']['data']['id']
            routeInfo = getRouteInfo(predictions, routeId)
            direction = routeInfo['attributes']['direction_destinations'][pred['attributes']['direction_id']]
            if direction == None:
                direction = 'unknown'
            return 'Departing ' + departureTime + ' from stop ' + stopName + ' towards ' + direction
    return 'No predicted departures'


if __name__ == '__main__':
    app.run(port= os.environ['PORT'])

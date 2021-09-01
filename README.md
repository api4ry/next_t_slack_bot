# /next_t

/next_t is a Slack Bot written in Python that allows you to request when the next T is leaving near you. The recording.gif file demonstrates how to use the bot.

## Set up

/next_t is a flask application. It exposes two web-hook end-points that need to be accessible to Slack.

A .env file should be used to store the API keys and secrets for the HERE geocoding service, Slack and MBTA APIs. All three services are required for the bot to function.

Once the bot is stood up, it needs to be added to the Slack instance and given the correct permissions. In Slack give the bot the following scope under the permissions section.
+ commands

A Slash Command can then be added under the name /next_t and the description "Next arrival time of the T". The Request URL is https://[domain of the server]/slash_command

The application also uses an Interactivity Request URL for responding to button selections. This needs to be activated and the correct end-point, /buttons, added to the Slack configuration.

## Usage

Call the bot using the slash command /next_t [your location]. If the location is within the MBTA service area, you will be prompted with buttons to select a stop near your location. The bot will then return the time of the next departure at that stop.

## How does it work?

The MBTA predictions API uses latitude and longitude as filters, most people don't know their current coordinates so the /next_t bot uses the HERE geocoding service to fetch the appropriate latitude and longitude based on a location provided by the user.

The latitude and longitude returned by the geocoding API is then sent to the predictions end point of the MBTA API. This end-point returns a sorted list of predictions within a half-mile radius of the provided location. The list is sorted by departure time, as vehicles arriving at terminal stations will have arrival times, but not departures, making their predictions not useful for someone looking to catch the bus. It is not possible to have the predictions end-point return the list sorted by location.

Once the list of predictions with valid departure times is fetched, a list of stops by route number is returned to the user as buttons. The bot sends the buttons over using Slack's block kit to compose the message, using the response URL provided by the original request to the Slash Command.

When a button is pressed a request is sent from Slack to the interactivity end-point of the bot, /buttons. This end-point consumes the JSON payload from Slack, and retrieves the selected stop ID. The bot is stateless and has no way of saving the prediction that was fetched in the first step. It then takes the stop ID and route ID from the request and makes a new call to the prediction API using the two IDs as filter values. That prediction is then formatted and sent to the user completing the workflow.

## How could be it be better?

The messages sent to the user could be formatted to be more clear. The time-stamp used for the departure time needs to be parsed and presented in a more user friendly format.

The app has only been deployed in a development environment, and needs to be configured for being deployed in a production environment.

The stops returned to the user should be sorted by distance from the requested location. While the predictions API does not sort by distance, the stop API does. Adding a sorting method that either sorts by latitude and longitude or by return order from the stop API would make the results more valuable to the user.

## Security concerns

/next_t is a stateless application that does not store user data, or perform its own database queries. While user input is handled, it is passed on to third party services where the expectation is that those services are properly handling the input.

The application does handle secrets used for authenticating with the third party services it uses. These secrets are stored in a .env file to keep them out of the code. These secrets could be secured further by keeping them encrypted at rest, either through a vault service or through encrypting them on disk.

The bot does take in location information and the interactivity web-hook request from Slack does contain user information. If the username was logged along with the location data, there could be some privacy concerns depending on how that data was stored and who had access to it. With info level logging that data is not logged, and the bot does not store data in any other way.

## External APIs used
+ https://api.slack.com/
+ https://developer.here.com/documentation/geocoding-search-api/api-reference-swagger.html
+ https://www.mbta.com/developers/v3-api
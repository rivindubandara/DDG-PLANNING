import imports

mapbox_access_token = 'pk.eyJ1Ijoicml2aW5kdWIiLCJhIjoiY2xmYThkcXNjMHRkdDQzcGU4Mmh2a3Q3MSJ9.dXlhamKyYyGusL3PWqDD9Q'

RHINO_COMPUTE_KEY="RhinoComputeKey"
API_SECRET="8c96f7d9-5a62-4bbf-ad3f-6e976b94ea1e"
COMPUTE_URL="http://13.54.229.195:80/"
SPECKLE_TOKEN="ff241e54658475cc2c8a3a066bc53faaf95285993a"

api_key = RHINO_COMPUTE_KEY
api_secret = API_SECRET
compute_url = COMPUTE_URL
speckleToken = SPECKLE_TOKEN

headers = {
    api_key: api_secret
}

# mercator transformers
transformer2 = imports.Transformer.from_crs("EPSG:4326", "EPSG:32756", always_xy=True)
transformer2_vic = imports.Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)

#isochrone variables
profile1 = 'mapbox/walking'
profile2 = 'mapbox/cycling'
profile3 = 'mapbox/driving'


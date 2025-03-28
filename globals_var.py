import imports

# Load environment variables
imports.load_dotenv()

# Get environment variables
mapbox_access_token = imports.os.getenv('MAPBOX_ACCESS_TOKEN')
RHINO_COMPUTE_KEY = imports.os.getenv('RHINO_COMPUTE_KEY')
API_SECRET = imports.os.getenv('API_SECRET')
COMPUTE_URL = imports.os.getenv('COMPUTE_URL')
SPECKLE_TOKEN = imports.os.getenv('SPECKLE_TOKEN')

# Use the environment variables
api_key = RHINO_COMPUTE_KEY
api_secret = API_SECRET
compute_url = COMPUTE_URL
speckleToken = SPECKLE_TOKEN

headers = {
    api_key: api_secret
}

# mercator transformers
transformer2 = imports.Transformer.from_crs(
    "EPSG:4326", "EPSG:32756", always_xy=True)
transformer2_vic = imports.Transformer.from_crs(
    "EPSG:4326", "EPSG:32755", always_xy=True)

# isochrone variables
profile1 = 'mapbox/walking'
profile2 = 'mapbox/cycling'
profile3 = 'mapbox/driving'

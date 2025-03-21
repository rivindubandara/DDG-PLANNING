import globals_var
import urls
import imports
import functions
import dicts

from flask import render_template, redirect, url_for, flash, request, send_file
import requests
import aiohttp
import asyncio

geoutils = functions.GeoUtils()
datafetcher = functions.DataFetcher()
computeapi = functions.ComputeAPI()
rhinoutils = functions.RhinoUtils()
mapboxfetcher = functions.MapboxFetcher()
gisparameters = functions.GISParameters()


def register_routes(application):
    @application.route('/', methods=['GET', 'POST'])
    def index():
        return render_template('index.html')

    @application.route('/nsw', methods=['GET', 'POST'])
    def nsw():
        return render_template('nsw.html', lat=-33.82267, lon=151.20124, state_name='NEW SOUTH WALES')

    @application.route('/qld', methods=['GET', 'POST'])
    def qld():
        return render_template('qld.html', lat=-27.462308, lon=153.028443, state_name='QUEENSLAND')

    @application.route('/vic', methods=['GET', 'POST'])
    def vic():
        return render_template('vic.html', lat=-37.8212907, lon=144.9451695, state_name='VICTORIA')

    @application.route('/tas', methods=['GET', 'POST'])
    def tas():
        return render_template('tas.html', lat=-42.880554, lon=147.324997, state_name='TASMANIA')

    @application.route('/act', methods=['GET', 'POST'])
    def act():
        return render_template('act.html', lat=-35.2802, lon=149.1310, state_name='AUSTRALIAN CAPITAL TERRITORY')

    @application.route('/nsw_planning', methods=['GET', 'POST'])
    def nsw_planning():

        # Geocoding
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }

        response = imports.requests.get(
            urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                error_message = "There is something wrong with your address, either you have not dropped a marker or the address is invalid."
                return imports.jsonify(error=error_message)

        # Boundary calculations
        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        b_xmin_LL, b_xmax_LL, b_ymin_LL, b_ymax_LL = geoutils.create_boundary(
            lat, lon, 20000)
        n_xmin_LL, n_xmax_LL, n_ymin_LL, n_ymax_LL = geoutils.create_boundary(
            lat, lon, 800000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)
        ras_xmin_LL, ras_xmax_LL, ras_ymin_LL, ras_ymax_LL = geoutils.create_boundary(
            lat, lon, 1000)

        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        b_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', b_xmin_LL, b_ymin_LL, b_xmax_LL, b_ymax_LL, '32756')
        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32756')
        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        native_post = {
            'maps': 'territories',
            'polygon_geojson': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [
                                [
                                    [n_xmin_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymin_LL]
                                ]
                            ]
                        }
                    }
                ]
            }
        }

        # Model and layer setup
        planning_model = imports.rh.File3dm()
        planning_model.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        planning_layerIndex = rhinoutils.create_layer(
            planning_model, "PLANNING", (237, 0, 194, 255))
        geometry_layerIndex = rhinoutils.create_layer(
            planning_model, "GEOMETRY", (237, 0, 194, 255))
        elevated_layerIndex = rhinoutils.create_layer(
            planning_model, "ELEVATED", (237, 0, 194, 255))
        boundary_layerIndex = rhinoutils.create_layer(
            planning_model, "BOUNDARY", (237, 0, 194, 255), planning_layerIndex)
        admin_layerIndex = rhinoutils.create_layer(
            planning_model, "ADMIN", (134, 69, 255, 255), planning_layerIndex)
        native_layerIndex = rhinoutils.create_layer(
            planning_model, "NATIVE", (134, 69, 255, 255), planning_layerIndex)
        zoning_layerIndex = rhinoutils.create_layer(
            planning_model, "ZONING", (255, 180, 18, 255), planning_layerIndex)
        hob_layerIndex = rhinoutils.create_layer(
            planning_model, "HOB", (204, 194, 173, 255), planning_layerIndex)
        lotsize_layerIndex = rhinoutils.create_layer(
            planning_model, "MLS", (224, 155, 177, 255), planning_layerIndex)
        fsr_layerIndex = rhinoutils.create_layer(
            planning_model, "FSR", (173, 35, 204, 255), planning_layerIndex)
        lots_layerIndex = rhinoutils.create_layer(
            planning_model, "LOTS", (255, 106, 0, 255), planning_layerIndex)
        road_layerIndex = rhinoutils.create_layer(
            planning_model, "ROADS", (145, 145, 145, 255), planning_layerIndex)
        walking_layerIndex = rhinoutils.create_layer(
            planning_model, "WALKING", (129, 168, 0, 255), planning_layerIndex)
        cycling_layerIndex = rhinoutils.create_layer(
            planning_model, "CYCLING", (0, 168, 168, 255), planning_layerIndex)
        driving_layerIndex = rhinoutils.create_layer(
            planning_model, "DRIVING", (168, 0, 121, 255), planning_layerIndex)
        bushfire_layerIndex = rhinoutils.create_layer(
            planning_model, "BUSHFIRE", (176, 7, 7, 255), planning_layerIndex)
        heritage_layerIndex = rhinoutils.create_layer(
            planning_model, "HERITAGE", (153, 153, 153, 255), planning_layerIndex)
        # raster_layerIndex = rhinoutils.create_layer(
        #     planning_model, "RASTER", (0, 204, 0, 255), planning_layerIndex)
        building_layerIndex = rhinoutils.create_layer(
            planning_model, "BUILDINGS", (99, 99, 99, 255), geometry_layerIndex)
        contours_layerIndex = rhinoutils.create_layer(
            planning_model, "CONTOURS", (191, 191, 191, 255), geometry_layerIndex)
        boundary_layerEIndex = rhinoutils.create_layer(
            planning_model, "BOUNDARY ELEVATED", (237, 0, 194, 255), elevated_layerIndex)
        building_layer_EIndex = rhinoutils.create_layer(
            planning_model, "BUILDINGS ELEVATED", (99, 99, 99, 255), elevated_layerIndex)
        topography_layerIndex = rhinoutils.create_layer(
            planning_model, "TOPOGRAPHY", (191, 191, 191, 255), elevated_layerIndex)
        contours_layer_EIndex = rhinoutils.create_layer(
            planning_model, "CONTOURS ELEVATED", (191, 191, 191, 255), elevated_layerIndex)


        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.nsw_adminboundaries_url: params,
            urls.nsw_zoning_url: params,
            urls.nsw_hob_url: b_params,
            urls.nsw_lotsize_url: b_params,
            urls.nsw_fsr_url: b_params,
            urls.nsw_lots_url: b_params,
            urls.nsw_bushfire_url: b_params,
            urls.nsw_heritage_url: b_params,
            urls.nsw_topo_url: topo_params
        }

        MAX_RETRIES = 3  # Maximum retries
        INITIAL_BACKOFF = 1  # Initial backoff in seconds

        async def fetch_paginated_data(session, url, params):
            """Fetch all paginated results from an API."""
            all_features = []
            while True:
                try:
                    async with session.get(url, params=params, timeout=30) as response:
                        if response.status == 200:
                            text = await response.text()
                            data = imports.json.loads(text)

                            # Append features from the current page
                            if "features" in data and data["features"]:
                                all_features.extend(data["features"])
                            else:
                                break

                            # Check for the next page (example with a 'next' key)
                            next_page_url = data.get("next")
                            if not next_page_url:
                                break

                            # Update the URL or parameters for the next page
                            url = next_page_url
                        else:
                            break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    break
                except Exception as e:
                    break

            return {"features": all_features}

        async def fetch_data(session, url, params, retries=MAX_RETRIES):
            """Fetch data with retry mechanism and pagination support."""
            attempt = 0
            while attempt < retries:
                try:
                    # Handle paginated URLs
                    if url in [urls.nsw_lots_url, urls.nsw_zoning_url]:
                        return await fetch_paginated_data(session, url, params)

                    # Regular API fetch
                    async with session.get(url, params=params, timeout=30) as response:
                        if response.status == 200:
                            text = await response.text()
                            try:
                                data = imports.json.loads(text)
                                return data
                            except imports.json.JSONDecodeError:
                                return None
                        else:
                            print(
                                f"Non-200 response ({response.status}), attempt {attempt + 1} for {url}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    print(
                        f"Network error: {e}, attempt {attempt + 1} for {url}")
                except Exception as e:
                    print(
                        f"Unexpected error: {e}, attempt {attempt + 1} for {url}")

                # Increment retry count and apply exponential backoff
                attempt += 1
                backoff_time = INITIAL_BACKOFF * \
                    (2 ** (attempt - 1)) + imports.random.uniform(0, 1)
                await asyncio.sleep(backoff_time)

            # If all retries fail
            return None

        async def fetch_all_data_with_validation(urls_dict):
            """Fetch data from all URLs with validation and retries."""
            async with aiohttp.ClientSession() as session:
                tasks = [
                    fetch_data(session, url, params)
                    for url, params in urls_dict.items()
                ]
                results = await asyncio.gather(*tasks)

                data_dict = {}
                for url, result in zip(urls_dict.keys(), results):
                    if result is not None:
                        if url == urls.nsw_adminboundaries_url:
                            data_dict['admin_data'] = result
                        elif url == urls.nsw_zoning_url:
                            data_dict['zoning_data'] = result
                        elif url == urls.nsw_hob_url:
                            data_dict['hob_data'] = result
                        elif url == urls.nsw_lotsize_url:
                            data_dict['lotsize_data'] = result
                        elif url == urls.nsw_fsr_url:
                            data_dict['fsr_data'] = result
                        elif url == urls.nsw_lots_url:
                            data_dict['lots_data'] = result
                        elif url == urls.nsw_bushfire_url:
                            data_dict['bushfire_data'] = result
                        elif url == urls.nsw_heritage_url:
                            data_dict['heritage_data'] = result
                        elif url == urls.nsw_topo_url:
                            data_dict['topography_data'] = result
                return data_dict

        # Data fetching
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Replace `params_dict` with your actual parameters dictionary
        data_dict = loop.run_until_complete(
            fetch_all_data_with_validation(params_dict))

        admin_data = data_dict.get('admin_data')
        zoning_data = data_dict.get('zoning_data')
        hob_data = data_dict.get('hob_data')
        lotsize_data = data_dict.get('lotsize_data')
        fsr_data = data_dict.get('fsr_data')
        lots_data = data_dict.get('lots_data')
        bushfire_data = data_dict.get('bushfire_data')
        heritage_data = data_dict.get('heritage_data')
        topography_data = data_dict.get('topography_data')

        # BOUNDARY
        boundary_data = datafetcher.get_data(
            urls.nsw_boundary_url, boundary_params)
        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, planning_model)

        # LOTS
        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'plannumber', planning_model)

        # HERITAGE
        rhinoutils.add_to_model(
            heritage_data, heritage_layerIndex, 'H_NAME', planning_model)

        # ADMIN
        rhinoutils.add_to_model(admin_data, admin_layerIndex,
                                'suburbname', planning_model)

        # Then the original call
        rhinoutils.curve_to_surface(zoning_data, zoning_layerIndex,
                                    'SYM_CODE', 'SYM_CODE', planning_model, dicts.nsw_zoning_dict)

        # MLS
        rhinoutils.curve_to_surface(
            lotsize_data, lotsize_layerIndex, 'SYM_CODE', 'LOT_SIZE', planning_model, dicts.nsw_mls_dict)

        # FSR
        rhinoutils.curve_to_surface(
            fsr_data, fsr_layerIndex, 'SYM_CODE', 'FSR', planning_model, dicts.nsw_fsr_dict)

        # HOB
        rhinoutils.curve_to_surface(
            hob_data, hob_layerIndex, 'SYM_CODE', 'MAX_B_H', planning_model, dicts.nsw_hob_dict)

        # Bushfire
        rhinoutils.curve_to_surface(bushfire_data, bushfire_layerIndex,
                                    'Category', 'd_Category', planning_model, dicts.nsw_bushfire_dict)

        # Native
        rhinoutils.add_native(urls.native_url, native_post, native_layerIndex,
                              planning_model, transformer=globals_var.transformer2)

        # Roads
        rhinoutils.add_roads_to_model(
            tiles, zoom, road_layerIndex, planning_model, transformer=globals_var.transformer2)

        # Isochrone processing
        longitude_iso = lon
        latitude_iso = lat

        iso_url_w = f'https://api.mapbox.com/isochrone/v1/{globals_var.profile1}/{longitude_iso}, {latitude_iso}?contours_minutes=5&polygons=true&access_token={globals_var.mapbox_access_token}'
        iso_url_c = f'https://api.mapbox.com/isochrone/v1/{globals_var.profile2}/{longitude_iso}, {latitude_iso}?contours_minutes=10&polygons=true&access_token={globals_var.mapbox_access_token}'
        iso_url_d = f'https://api.mapbox.com/isochrone/v1/{globals_var.profile3}/{longitude_iso}, {latitude_iso}?contours_minutes=15&polygons=true&access_token={globals_var.mapbox_access_token}'

        iso_response_w = imports.requests.get(iso_url_w)
        walking_data = imports.json.loads(iso_response_w.content.decode())

        iso_response_c = imports.requests.get(iso_url_c)
        cycling_data = imports.json.loads(iso_response_c.content.decode())

        iso_response_d = imports.requests.get(iso_url_d)
        driving_data = imports.json.loads(iso_response_d.content.decode())

        # Walking Curves
        rhinoutils.add_isochrone_to_model(
            walking_data, walking_layerIndex, planning_model, transformer=globals_var.transformer2)

        # Cycling Curves
        rhinoutils.add_isochrone_to_model(
            cycling_data, cycling_layerIndex, planning_model, transformer=globals_var.transformer2)

        # Driving Curves
        rhinoutils.add_isochrone_to_model(
            driving_data, driving_layerIndex, planning_model, transformer=globals_var.transformer2)

        # ras_tiles = list(imports.mercantile.tiles(ras_xmin_LL, ras_ymin_LL,
        #                                           ras_xmax_LL, ras_ymax_LL, zooms=16))

        # rhinoutils.add_raster(ras_tiles, zoom, gh_raster_decoded,
        #                       raster_layerIndex, planning_model, transformer=globals.transformer2)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, planning_model, transformer=globals_var.transformer2)

        # topography
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, planning_model, 'elevation')

        # giraffe
        if 'giraffeInput' in request.files:
            giraffe_file = request.files['giraffeInput']
            rhinoutils.giraffe(giraffe_file, planning_model,
                               transformer=globals_var.transformer2)
        else:
            pass

        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'elevation', contours_layer_EIndex,
                                                  planning_model, globals_var.transformer2, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex,
                                      bound_curve, gh_buildings_elevated_decoded, planning_model, globals_var.transformer2, mesh_geo_list)

        cen_x, cen_y = globals_var.transformer2.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(
            -centroid.X, -centroid.Y, -centroid.Z)

        for obj in planning_model.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)

        filename = "planning.3dm"
        file_path = imports.os.path.abspath(
            imports.os.path.join('tmp', 'files', filename))
        planning_model.Write(file_path, 7)

        return send_file(file_path, as_attachment=True)

    @application.route('/qld_planning', methods=['GET', 'POST'])
    def qld_planning():
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }

        response = imports.requests.get(
            urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                error_message = "There is something wrong with your address, either you have not dropped a marker or the address is invalid."
                return imports.jsonify(error=error_message)

        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        r_xmin_LL, r_xmax_LL, r_ymin_LL, r_ymax_LL = geoutils.create_boundary(
            lat, lon, 60000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)
        n_xmin_LL, n_xmax_LL, n_ymin_LL, n_ymax_LL = geoutils.create_boundary(
            lat, lon, 800000)
        ras_xmin_LL, ras_xmax_LL, ras_ymin_LL, ras_ymax_LL = geoutils.create_boundary(
            lat, lon, 1000)

        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32756')
        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        r_params = {
            'where': '1=1',
            'geometry': f'{r_xmin_LL}, {r_ymin_LL},{r_xmax_LL},{r_ymax_LL}',
            'geometryType': 'esriGeometryEnvelope',
            'spatialRel': 'esriSpatialRelContains',
            'returnGeometry': 'true',
            'f': 'json',
            'outFields': '*',
            'inSR': '4326',
            'outSR': '32756',

        }

        native_post = {
            'maps': 'territories',
            'polygon_geojson': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [
                                [
                                    [n_xmin_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymin_LL]
                                ]
                            ]
                        }
                    }
                ]
            }
        }
        qld_planning = imports.rh.File3dm()
        qld_planning.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        planning_layerIndex = rhinoutils.create_layer(
            qld_planning, "PLANNING", (237, 0, 194, 255))
        geometry_layerIndex = rhinoutils.create_layer(
            qld_planning, "GEOMETRY", (237, 0, 194, 255))
        elevated_layerIndex = rhinoutils.create_layer(
            qld_planning, "ELEVATED", (237, 0, 194, 255))
        boundary_layerIndex = rhinoutils.create_layer(
            qld_planning, "BOUNDARY", (237, 0, 194, 255), planning_layerIndex)
        admin_layerIndex = rhinoutils.create_layer(
            qld_planning, "ADMIN", (134, 69, 255, 255), planning_layerIndex)
        native_layerIndex = rhinoutils.create_layer(
            qld_planning, "NATIVE", (134, 69, 255, 255), planning_layerIndex)
        zoning_layerIndex = rhinoutils.create_layer(
            qld_planning, "ZONING", (255, 180, 18, 255), planning_layerIndex)
        overlandflow_layerIndex = rhinoutils.create_layer(
            qld_planning, "OVERLAND FLOW", (255, 106, 0, 255), planning_layerIndex)
        creek_layerIndex = rhinoutils.create_layer(
            qld_planning, "CREEK/WATERWAY FLOOD", (255, 106, 0, 255), planning_layerIndex)
        river_layerIndex = rhinoutils.create_layer(
            qld_planning, "RIVER FLOOD", (255, 106, 0, 255), planning_layerIndex)
        lots_layerIndex = rhinoutils.create_layer(
            qld_planning, "LOTS", (255, 106, 0, 255), planning_layerIndex)
        road_layerIndex = rhinoutils.create_layer(
            qld_planning, "ROADS", (145, 145, 145, 255), planning_layerIndex)
        walking_layerIndex = rhinoutils.create_layer(
            qld_planning, "WALKING", (129, 168, 0, 255), planning_layerIndex)
        cycling_layerIndex = rhinoutils.create_layer(
            qld_planning, "CYCLING", (0, 168, 168, 255), planning_layerIndex)
        driving_layerIndex = rhinoutils.create_layer(
            qld_planning, "DRIVING", (168, 0, 121, 255), planning_layerIndex)
        bushfire_layerIndex = rhinoutils.create_layer(
            qld_planning, "BUSHFIRE", (176, 7, 7, 255), planning_layerIndex)
        heritage_layerIndex = rhinoutils.create_layer(
            qld_planning, "HERITAGE", (153, 153, 153, 255), planning_layerIndex)
        # raster_layerIndex = rhinoutils.create_layer(
        #     qld_planning, "RASTER", (0, 204, 0, 255), planning_layerIndex)
        building_layerIndex = rhinoutils.create_layer(
            qld_planning, "BUILDINGS", (99, 99, 99, 255), geometry_layerIndex)
        contours_layerIndex = rhinoutils.create_layer(
            qld_planning, "CONTOURS", (191, 191, 191, 255), geometry_layerIndex)
        boundary_layerEIndex = rhinoutils.create_layer(
            qld_planning, "BOUNDARY ELEVATED", (237, 0, 194, 255), elevated_layerIndex)
        building_layer_EIndex = rhinoutils.create_layer(
            qld_planning, "BUILDINGS ELEVATED", (99, 99, 99, 255), elevated_layerIndex)
        topography_layerIndex = rhinoutils.create_layer(
            qld_planning, "TOPOGRAPHY", (191, 191, 191, 255), elevated_layerIndex)
        contours_layer_EIndex = rhinoutils.create_layer(
            qld_planning, "CONTOURS ELEVATED", (191, 191, 191, 255), elevated_layerIndex)


        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.qld_adminboundaries_url: params,
            urls.qld_zoning_url: params,
            urls.qld_overflow_url: params,
            urls.qld_creek_url: params,
            urls.qld_heritage_url: params,
            urls.qld_bushfire_url: params,
            urls.qld_river_url: r_params,
            urls.qld_lots_url: params,
            urls.qld_topo_url: topo_params,
        }

        urls_list = [
            urls.qld_adminboundaries_url,
            urls.qld_zoning_url,
            urls.qld_overflow_url,
            urls.qld_creek_url,
            urls.qld_heritage_url,
            urls.qld_bushfire_url,
            urls.qld_river_url,
            urls.qld_lots_url,
            urls.qld_topo_url,
        ]

        data_dict = {}

        with imports.cf.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(
                datafetcher.get_data, url, params=params_dict[url]): url for url in urls_list}

            for future in imports.cf.as_completed(future_to_url):
                url = future_to_url[future]
                data = future.result()
                if data is not None:
                    if url == urls.qld_adminboundaries_url:
                        data_dict['admin_data'] = data
                    elif url == urls.qld_zoning_url:
                        data_dict['zoning_data'] = data
                    elif url == urls.qld_overflow_url:
                        data_dict['overflow_data'] = data
                    elif url == urls.qld_creek_url:
                        data_dict['creek_data'] = data
                    elif url == urls.qld_heritage_url:
                        data_dict['heritage_data'] = data
                    elif url == urls.qld_bushfire_url:
                        data_dict['bushfire_data'] = data
                    elif url == urls.qld_river_url:
                        data_dict['river_data'] = data
                    elif url == urls.qld_lots_url:
                        data_dict['lots_data'] = data
                    elif url == urls.qld_topo_url:
                        data_dict['topography_data'] = data

        admin_data = data_dict.get('admin_data')
        zoning_data = data_dict.get('zoning_data')
        overflow_data = data_dict.get('overflow_data')
        creek_data = data_dict.get('creek_data')
        heritage_data = data_dict.get('heritage_data')
        bushfire_data = data_dict.get('bushfire_data')
        river_data = data_dict.get('river_data')
        lots_data = data_dict.get('lots_data')
        topography_data = data_dict.get('topography_data')

        boundary_data = datafetcher.get_data(
            urls.qld_boundary_url, boundary_params)
        # BOUNDARY
        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, qld_planning)

        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'lotplan', qld_planning)

        rhinoutils.add_to_model(
            overflow_data, overlandflow_layerIndex, 'OVL2_CAT', qld_planning)

        rhinoutils.add_to_model(creek_data, creek_layerIndex,
                                'OVL2_CAT', qld_planning)

        # Admin
        rhinoutils.add_to_model(admin_data, admin_layerIndex,
                                'locality', qld_planning)

        rhinoutils.curve_to_surface(zoning_data, zoning_layerIndex,
                                    'qlump_code', 'qlump_code', qld_planning, dicts.qld_zoning_dict)
        # Bushfire
        rhinoutils.curve_to_surface(bushfire_data, bushfire_layerIndex,
                                    "OVL2_CAT", "OVL2_CAT", qld_planning, dicts.qld_bushfire_dict)

        rhinoutils.add_to_model(heritage_data, heritage_layerIndex,
                                'OVL2_CAT', qld_planning)

        # Native
        rhinoutils.add_native(urls.native_url, native_post, native_layerIndex,
                              qld_planning, transformer=globals.transformer2)

        # Roads
        rhinoutils.add_roads_to_model(
            tiles, zoom, road_layerIndex, qld_planning, transformer=globals.transformer2)

        # Isochrone
        longitude_iso = lon
        latitude_iso = lat

        iso_url_w = f'https://api.mapbox.com/isochrone/v1/{globals.profile1}/{longitude_iso}, {   latitude_iso}?contours_minutes=5&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_c = f'https://api.mapbox.com/isochrone/v1/{globals.profile2}/{longitude_iso}, { latitude_iso}?contours_minutes=10&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_d = f'https://api.mapbox.com/isochrone/v1/{globals.profile3}/{longitude_iso}, { latitude_iso}?contours_minutes=15&polygons=true&access_token={globals.mapbox_access_token}'

        iso_response_w = imports.requests.get(iso_url_w)
        walking_data = imports.json.loads(iso_response_w.content.decode())

        iso_response_c = imports.requests.get(iso_url_c)
        cycling_data = imports.json.loads(iso_response_c.content.decode())

        iso_response_d = imports.requests.get(iso_url_d)
        driving_data = imports.json.loads(iso_response_d.content.decode())

        # Walking Curves
        rhinoutils.add_isochrone_to_model(
            walking_data, walking_layerIndex, qld_planning, transformer=globals.transformer2)

        # Cycling Curves
        rhinoutils.add_isochrone_to_model(
            cycling_data, cycling_layerIndex, qld_planning, transformer=globals.transformer2)

        # Driving Curves
        rhinoutils.add_isochrone_to_model(
            driving_data, driving_layerIndex, qld_planning, transformer=globals.transformer2)

        # ras_tiles = list(imports.mercantile.tiles(ras_xmin_LL, ras_ymin_LL,
        #                                           ras_xmax_LL, ras_ymax_LL, zooms=16))

        # rhinoutils.add_raster(ras_tiles, zoom, gh_raster_decoded,
        #                       raster_layerIndex, qld_planning, transformer=globals.transformer2)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, qld_planning, transformer=globals.transformer2)

        # topography
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, qld_planning, 'elevation_m')

        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'elevation_m', contours_layer_EIndex,
                                                  qld_planning, globals.transformer2, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex,
                                      bound_curve, gh_buildings_elevated_decoded, qld_planning, globals.transformer2, mesh_geo_list)

        # giraffe
        if 'giraffeInput' in request.files:
            giraffe_file = request.files['giraffeInput']
            rhinoutils.giraffe(giraffe_file, qld_planning,
                               transformer=globals.transformer2)
        else:
            pass

        cen_x, cen_y = globals.transformer2.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(
            -centroid.X, -centroid.Y, -centroid.Z)

        for obj in qld_planning.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)

        filename = "qld_planning.3dm"
        file_path = imports.os.path.abspath(
            imports.os.path.join('tmp', 'files', filename))
        qld_planning.Write(file_path, 7)
        return send_file(file_path, as_attachment=True)

    @application.route('/vic_planning', methods=['GET', 'POST'])
    def vic_planning():
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }

        response = imports.requests.get(
            urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                error_message = "There is something wrong with your address, either you have not dropped a marker or the address is invalid."
                return imports.jsonify(error=error_message)

        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        n_xmin_LL, n_xmax_LL, n_ymin_LL, n_ymax_LL = geoutils.create_boundary(
            lat, lon, 800000)
        ras_xmin_LL, ras_xmax_LL, ras_ymin_LL, ras_ymax_LL = geoutils.create_boundary(
            lat, lon, 1000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)

        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32755')
        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32755')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32755')

        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        native_post = {
            'maps': 'territories',
            'polygon_geojson': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [
                                [
                                    [n_xmin_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymin_LL]
                                ]
                            ]
                        }
                    }
                ]
            }
        }

        vic_planning = imports.rh.File3dm()
        vic_planning.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        planning_layerIndex = rhinoutils.create_layer(
            vic_planning, "PLANNING", (237, 0, 194, 255))
        geometry_layerIndex = rhinoutils.create_layer(
            vic_planning, "GEOMETRY", (237, 0, 194, 255))
        elevated_layerIndex = rhinoutils.create_layer(
            vic_planning, "ELEVATED", (237, 0, 194, 255))
        boundary_layerIndex = rhinoutils.create_layer(
            vic_planning, "BOUNDARY", (237, 0, 194, 255), planning_layerIndex)
        admin_layerIndex = rhinoutils.create_layer(
            vic_planning, "ADMIN", (134, 69, 255, 255), planning_layerIndex)
        native_layerIndex = rhinoutils.create_layer(
            vic_planning, "NATIVE", (134, 69, 255, 255), planning_layerIndex)
        zoning_layerIndex = rhinoutils.create_layer(
            vic_planning, "ZONING", (255, 180, 18, 255), planning_layerIndex)
        lots_layerIndex = rhinoutils.create_layer(
            vic_planning, "LOTS", (255, 106, 0, 255), planning_layerIndex)
        road_layerIndex = rhinoutils.create_layer(
            vic_planning, "ROADS", (145, 145, 145, 255), planning_layerIndex)
        walking_layerIndex = rhinoutils.create_layer(
            vic_planning, "WALKING", (129, 168, 0, 255), planning_layerIndex)
        cycling_layerIndex = rhinoutils.create_layer(
            vic_planning, "CYCLING", (0, 168, 168, 255), planning_layerIndex)
        driving_layerIndex = rhinoutils.create_layer(
            vic_planning, "DRIVING", (168, 0, 121, 255), planning_layerIndex)
        bushfire_layerIndex = rhinoutils.create_layer(
            vic_planning, "BUSHFIRE", (176, 7, 7, 255), planning_layerIndex)
        heritage_layerIndex = rhinoutils.create_layer(
            vic_planning, "HERITAGE", (153, 153, 153, 255), planning_layerIndex)
        # raster_layerIndex = rhinoutils.create_layer(
        #     vic_planning, "RASTER", (0, 204, 0, 255), planning_layerIndex)
        building_layerIndex = rhinoutils.create_layer(
            vic_planning, "BUILDINGS", (99, 99, 99, 255), geometry_layerIndex)
        contours_layerIndex = rhinoutils.create_layer(
            vic_planning, "CONTOURS", (191, 191, 191, 255), geometry_layerIndex)
        boundary_layerEIndex = rhinoutils.create_layer(
            vic_planning, "BOUNDARY ELEVATED", (237, 0, 194, 255), elevated_layerIndex)
        building_layer_EIndex = rhinoutils.create_layer(
            vic_planning, "BUILDINGS ELEVATED", (99, 99, 99, 255), elevated_layerIndex)
        topography_layerIndex = rhinoutils.create_layer(
            vic_planning, "TOPOGRAPHY", (191, 191, 191, 255), elevated_layerIndex)
        contours_layer_EIndex = rhinoutils.create_layer(
            vic_planning, "CONTOURS ELEVATED", (191, 191, 191, 255), elevated_layerIndex)

        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.vic_adminboundaries_url: params,
            urls.vic_zoning_url: params,
            urls.vic_heritage_url: topo_params,
            urls.vic_bushfire_url: params,
            urls.vic_boundary_url: params,
            urls.vic_topo_url: topo_params,
        }

        urls_list = [
            urls.vic_adminboundaries_url,
            urls.vic_zoning_url,
            urls.vic_heritage_url,
            urls.vic_bushfire_url,
            urls.vic_boundary_url,
            urls.vic_topo_url,
        ]

        data_dict = {}

        with imports.cf.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(
                datafetcher.get_data, url, params=params_dict[url]): url for url in urls_list}

            for future in imports.cf.as_completed(future_to_url):
                url = future_to_url[future]
                data = future.result()
                if data is not None:
                    if url == urls.vic_adminboundaries_url:
                        data_dict['admin_data'] = data
                    elif url == urls.vic_zoning_url:
                        data_dict['zoning_data'] = data
                    elif url == urls.vic_heritage_url:
                        data_dict['heritage_data'] = data
                    elif url == urls.vic_bushfire_url:
                        data_dict['bushfire_data'] = data
                    elif url == urls.vic_boundary_url:
                        data_dict['lots_data'] = data
                    elif url == urls.vic_topo_url:
                        data_dict['topography_data'] = data

        admin_data = data_dict.get('admin_data')
        zoning_data = data_dict.get('zoning_data')
        heritage_data = data_dict.get('heritage_data')
        bushfire_data = data_dict.get('bushfire_data')
        lots_data = data_dict.get('lots_data')
        topography_data = data_dict.get('topography_data')

        boundary_data = datafetcher.get_data(
            urls.vic_boundary_url, boundary_params)

        # BOUNDARY
        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, vic_planning)

        # LOTS
        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'parcel_spi', vic_planning)

        # Admin
        rhinoutils.add_to_model(
            admin_data, admin_layerIndex, 'locality_name', vic_planning)

        # Zoning
        rhinoutils.curve_to_surface(
            zoning_data, zoning_layerIndex, 'ZONE_CODE_GROUP', 'ZONE_CODE_GROUP', vic_planning, dicts.vic_zoning_dict)

        # heritage
        rhinoutils.add_to_model(
            heritage_data, heritage_layerIndex, 'SITE_NAME', vic_planning)

        # Bushfire
        rhinoutils.curve_to_surface(bushfire_data, bushfire_layerIndex,
                                    "ZONE_CODE", "ZONE_CODE", vic_planning, dicts.vic_bushfire_dict)

        # Native
        rhinoutils.add_native(urls.native_url, native_post, native_layerIndex,
                              vic_planning, transformer=globals.transformer2_vic)

        # Roads
        rhinoutils.add_roads_to_model(
            tiles, zoom, road_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # Isochrone
        longitude_iso = lon
        latitude_iso = lat

        iso_url_w = f'https://api.mapbox.com/isochrone/v1/{globals.profile1}/{longitude_iso}, {latitude_iso}?contours_minutes=5&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_c = f'https://api.mapbox.com/isochrone/v1/{globals.profile2}/{longitude_iso}, { latitude_iso}?contours_minutes=10&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_d = f'https://api.mapbox.com/isochrone/v1/{globals.profile3}/{longitude_iso}, {latitude_iso}?contours_minutes=15&polygons=true&access_token={globals.mapbox_access_token}'

        iso_response_w = imports.requests.get(iso_url_w)
        walking_data = imports.json.loads(iso_response_w.content.decode())

        iso_response_c = imports.requests.get(iso_url_c)
        cycling_data = imports.json.loads(iso_response_c.content.decode())

        iso_response_d = imports.requests.get(iso_url_d)
        driving_data = imports.json.loads(iso_response_d.content.decode())

        # Walking Curves
        rhinoutils.add_isochrone_to_model(
            walking_data, walking_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # Cycling Curves
        rhinoutils.add_isochrone_to_model(
            cycling_data, cycling_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # Driving Curves
        rhinoutils.add_isochrone_to_model(
            driving_data, driving_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # ras_tiles = list(imports.mercantile.tiles(ras_xmin_LL, ras_ymin_LL,
        #                                           ras_xmax_LL, ras_ymax_LL, zooms=16))

        # rhinoutils.add_raster(ras_tiles, zoom, gh_raster_decoded,
        #                       raster_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, vic_planning, transformer=globals.transformer2_vic)

        # topography
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, vic_planning, 'altitude')

        # giraffe
        if 'giraffeInput' in request.files:
            giraffe_file = request.files['giraffeInput']
            rhinoutils.giraffe(giraffe_file, vic_planning,
                               transformer=globals.transformer2_vic)
        else:
            pass

        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'altitude', contours_layer_EIndex,
                                                  vic_planning, globals.transformer2_vic, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex, bound_curve,
                                      gh_buildings_elevated_decoded, vic_planning, globals.transformer2_vic, mesh_geo_list)

        cen_x, cen_y = globals.transformer2_vic.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(
            -centroid.X, -centroid.Y, -centroid.Z)

        for obj in vic_planning.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)
        filename = "vic_planning.3dm"
        file_path = imports.os.path.abspath(
            imports.os.path.join('tmp', 'files', filename))
        vic_planning.Write(file_path, 7)
        return send_file(file_path, as_attachment=True)

    @application.route('/tas_planning', methods=['GET', 'POST'])
    def tas_planning():
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }

        response = imports.requests.get(
            urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                error_message = "There is something wrong with your address, either you have not dropped a marker or the address is invalid."
                return imports.jsonify(error=error_message)

        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        l_xmin_LL, l_xmax_LL, l_ymin_LL, l_ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        n_xmin_LL, n_xmax_LL, n_ymin_LL, n_ymax_LL = geoutils.create_boundary(
            lat, lon, 800000)
        ras_xmin_LL, ras_xmax_LL, ras_ymin_LL, ras_ymax_LL = geoutils.create_boundary(
            lat, lon, 1000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)

        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32755')
        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32755')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32755')

        l_params = {
            'where': '1=1',
            'geometry': f'{l_xmin_LL}, {l_ymin_LL},{l_xmax_LL},{l_ymax_LL}',
            'geometryType': 'esriGeometryEnvelope',
            'spatialRel': 'esriSpatialRelContains',
            'returnGeometry': 'true',
            'f': 'json',
            'outFields': '*',
            'inSR': '4326',
            'outSR': '32755',
        }

        native_post = {
            'maps': 'territories',
            'polygon_geojson': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [
                                [
                                    [n_xmin_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymin_LL]
                                ]
                            ]
                        }
                    }
                ]
            }
        }

        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        tas_planning = imports.rh.File3dm()
        tas_planning.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        planning_layerIndex = rhinoutils.create_layer(
            tas_planning, "PLANNING", (237, 0, 194, 255))
        geometry_layerIndex = rhinoutils.create_layer(
            tas_planning, "GEOMETRY", (237, 0, 194, 255))
        elevated_layerIndex = rhinoutils.create_layer(
            tas_planning, "ELEVATED", (237, 0, 194, 255))
        boundary_layerIndex = rhinoutils.create_layer(
            tas_planning, "BOUNDARY", (237, 0, 194, 255), planning_layerIndex)
        admin_layerIndex = rhinoutils.create_layer(
            tas_planning, "ADMIN", (134, 69, 255, 255), planning_layerIndex)
        native_layerIndex = rhinoutils.create_layer(
            tas_planning, "NATIVE", (134, 69, 255, 255), planning_layerIndex)
        zoning_layerIndex = rhinoutils.create_layer(
            tas_planning, "ZONING", (255, 180, 18, 255), planning_layerIndex)
        lots_layerIndex = rhinoutils.create_layer(
            tas_planning, "LOTS", (255, 106, 0, 255), planning_layerIndex)
        road_layerIndex = rhinoutils.create_layer(
            tas_planning, "ROADS", (145, 145, 145, 255), planning_layerIndex)
        walking_layerIndex = rhinoutils.create_layer(
            tas_planning, "WALKING", (129, 168, 0, 255), planning_layerIndex)
        cycling_layerIndex = rhinoutils.create_layer(
            tas_planning, "CYCLING", (0, 168, 168, 255), planning_layerIndex)
        driving_layerIndex = rhinoutils.create_layer(
            tas_planning, "DRIVING", (168, 0, 121, 255), planning_layerIndex)
        bushfire_layerIndex = rhinoutils.create_layer(
            tas_planning, "BUSHFIRE", (176, 7, 7, 255), planning_layerIndex)
        heritage_layerIndex = rhinoutils.create_layer(
            tas_planning, "HERITAGE", (153, 153, 153, 255), planning_layerIndex)
        # raster_layerIndex = rhinoutils.create_layer(
        #     vic_planning, "RASTER", (0, 204, 0, 255), planning_layerIndex)
        building_layerIndex = rhinoutils.create_layer(
            tas_planning, "BUILDINGS", (99, 99, 99, 255), geometry_layerIndex)
        contours_layerIndex = rhinoutils.create_layer(
            tas_planning, "CONTOURS", (191, 191, 191, 255), geometry_layerIndex)
        boundary_layerEIndex = rhinoutils.create_layer(
            tas_planning, "BOUNDARY ELEVATED", (237, 0, 194, 255), elevated_layerIndex)
        building_layer_EIndex = rhinoutils.create_layer(
            tas_planning, "BUILDINGS ELEVATED", (99, 99, 99, 255), elevated_layerIndex)
        topography_layerIndex = rhinoutils.create_layer(
            tas_planning, "TOPOGRAPHY", (191, 191, 191, 255), elevated_layerIndex)
        contours_layer_EIndex = rhinoutils.create_layer(
            tas_planning, "CONTOURS ELEVATED", (191, 191, 191, 255), elevated_layerIndex)

        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.tas_boundary_url: l_params,
            urls.tas_adminboundaries_url: params,
            urls.tas_zoning_url: params,
            urls.tas_heritage_url: params,
            urls.tas_topo_url: topo_params
        }

        urls_list = [
            urls.tas_boundary_url,
            urls.tas_adminboundaries_url,
            urls.tas_zoning_url,
            urls.tas_heritage_url,
            urls.tas_topo_url
        ]

        data_dict = {}

        with imports.cf.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(
                datafetcher.get_data, url, params=params_dict[url]): url for url in urls_list}

            for future in imports.cf.as_completed(future_to_url):
                url = future_to_url[future]
                data = future.result()
                if data is not None:
                    if url == urls.tas_adminboundaries_url:
                        data_dict['admin_data'] = data
                    elif url == urls.tas_zoning_url:
                        data_dict['zoning_data'] = data
                    elif url == urls.tas_boundary_url:
                        data_dict['lots_data'] = data
                    elif url == urls.tas_heritage_url:
                        data_dict['heritage_data'] = data
                    elif url == urls.tas_topo_url:
                        data_dict['topography_data'] = data

        admin_data = data_dict.get('admin_data')
        zoning_data = data_dict.get('zoning_data')
        heritage_data = data_dict.get('heritage_data')
        lots_data = data_dict.get('lots_data')
        topography_data = data_dict.get('topography_data')

        boundary_data = datafetcher.get_data(
            urls.tas_boundary_url, boundary_params)

        # BOUNDARY
        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, tas_planning)

        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'PID', tas_planning)

        # Admin
        rhinoutils.add_to_model(
            admin_data, admin_layerIndex, 'NAME', tas_planning)

        # Zoning
        rhinoutils.curve_to_surface(
            zoning_data, zoning_layerIndex, 'ZONECODE', 'ZONECODE', tas_planning, dicts.tas_zoning_dict)

        # Native
        rhinoutils.add_native(urls.native_url, native_post, native_layerIndex,
                              tas_planning, transformer=globals.transformer2_vic)

        # Roads
        rhinoutils.add_roads_to_model(tiles, zoom,
                                      road_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # Heritage
        rhinoutils.add_to_model(
            heritage_data, heritage_layerIndex, 'THR_NAME', tas_planning)

        # Isochrone
        longitude_iso = lon
        latitude_iso = lat

        iso_url_w = f'https://api.mapbox.com/isochrone/v1/{globals.profile1}/{longitude_iso}, { latitude_iso}?contours_minutes=5&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_c = f'https://api.mapbox.com/isochrone/v1/{globals.profile2}/{longitude_iso}, { latitude_iso}?contours_minutes=10&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_d = f'https://api.mapbox.com/isochrone/v1/{globals.profile3}/{longitude_iso}, { latitude_iso}?contours_minutes=15&polygons=true&access_token={globals.mapbox_access_token}'

        iso_response_w = imports.requests.get(iso_url_w)
        walking_data = imports.json.loads(iso_response_w.content.decode())

        iso_response_c = imports.requests.get(iso_url_c)
        cycling_data = imports.json.loads(iso_response_c.content.decode())

        iso_response_d = imports.requests.get(iso_url_d)
        driving_data = imports.json.loads(iso_response_d.content.decode())

        # Walking Curves
        rhinoutils.add_isochrone_to_model(
            walking_data, walking_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # Cycling Curves
        rhinoutils.add_isochrone_to_model(
            cycling_data, cycling_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # Driving Curves
        rhinoutils.add_isochrone_to_model(
            driving_data, driving_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # ras_tiles = list(imports.mercantile.tiles(ras_xmin_LL, ras_ymin_LL,
        #                                           ras_xmax_LL, ras_ymax_LL, zooms=16))

        # rhinoutils.add_raster(ras_tiles, zoom, gh_raster_decoded,
        #                       raster_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, tas_planning, transformer=globals.transformer2_vic)

        # topography
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, tas_planning, 'ELEVATION')

        # giraffe
        if 'giraffeInput' in request.files:
            giraffe_file = request.files['giraffeInput']
            rhinoutils.giraffe(giraffe_file, tas_planning,
                               transformer=globals.transformer2_vic)
        else:
            pass

        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'ELEVATION', contours_layer_EIndex,
                                                  tas_planning, globals.transformer2_vic, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex,
                                      bound_curve, gh_buildings_elevated_decoded, tas_planning, globals.transformer2_vic, mesh_geo_list)

        cen_x, cen_y = globals.transformer2_vic.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(
            -centroid.X, -centroid.Y, -centroid.Z)

        for obj in tas_planning.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)

        filename = "tas_planning.3dm"
        file_path = imports.os.path.abspath(
            imports.os.path.join('tmp', 'files', filename))
        tas_planning.Write(file_path, 7)
        return send_file(file_path, as_attachment=True)

    @application.route('/act_planning', methods=['GET', 'POST'])
    def act_planning():
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }

        response = imports.requests.get(
            urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                error_message = "There is something wrong with your address, either you have not dropped a marker or the address is invalid."
                return imports.jsonify(error=error_message)

        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        l_xmin_LL, l_xmax_LL, l_ymin_LL, l_ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        n_xmin_LL, n_xmax_LL, n_ymin_LL, n_ymax_LL = geoutils.create_boundary(
            lat, lon, 800000)
        ras_xmin_LL, ras_xmax_LL, ras_ymin_LL, ras_ymax_LL = geoutils.create_boundary(
            lat, lon, 1000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)

        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32756')

        native_post = {
            'maps': 'territories',
            'polygon_geojson': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [
                                [
                                    [n_xmin_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymin_LL],
                                    [n_xmax_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymax_LL],
                                    [n_xmin_LL, n_ymin_LL]
                                ]
                            ]
                        }
                    }
                ]
            }
        }

        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        act_planning = imports.rh.File3dm()
        act_planning.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        planning_layerIndex = rhinoutils.create_layer(
            act_planning, "PLANNING", (237, 0, 194, 255))
        geometry_layerIndex = rhinoutils.create_layer(
            act_planning, "GEOMETRY", (237, 0, 194, 255))
        elevated_layerIndex = rhinoutils.create_layer(
            act_planning, "ELEVATED", (237, 0, 194, 255))
        boundary_layerIndex = rhinoutils.create_layer(
            act_planning, "BOUNDARY", (237, 0, 194, 255), planning_layerIndex)
        admin_layerIndex = rhinoutils.create_layer(
            act_planning, "ADMIN", (134, 69, 255, 255), planning_layerIndex)
        native_layerIndex = rhinoutils.create_layer(
            act_planning, "NATIVE", (134, 69, 255, 255), planning_layerIndex)
        zoning_layerIndex = rhinoutils.create_layer(
            act_planning, "ZONING", (255, 180, 18, 255), planning_layerIndex)
        lots_layerIndex = rhinoutils.create_layer(
            act_planning, "LOTS", (255, 106, 0, 255), planning_layerIndex)
        road_layerIndex = rhinoutils.create_layer(
            act_planning, "ROADS", (145, 145, 145, 255), planning_layerIndex)
        walking_layerIndex = rhinoutils.create_layer(
            act_planning, "WALKING", (129, 168, 0, 255), planning_layerIndex)
        cycling_layerIndex = rhinoutils.create_layer(
            act_planning, "CYCLING", (0, 168, 168, 255), planning_layerIndex)
        driving_layerIndex = rhinoutils.create_layer(
            act_planning, "DRIVING", (168, 0, 121, 255), planning_layerIndex)
        bushfire_layerIndex = rhinoutils.create_layer(
            act_planning, "BUSHFIRE", (176, 7, 7, 255), planning_layerIndex)
        heritage_layerIndex = rhinoutils.create_layer(
            act_planning, "HERITAGE", (153, 153, 153, 255), planning_layerIndex)
        # raster_layerIndex = rhinoutils.create_layer(
        #     vic_planning, "RASTER", (0, 204, 0, 255), planning_layerIndex)
        building_layerIndex = rhinoutils.create_layer(
            act_planning, "BUILDINGS", (99, 99, 99, 255), geometry_layerIndex)
        contours_layerIndex = rhinoutils.create_layer(
            act_planning, "CONTOURS", (191, 191, 191, 255), geometry_layerIndex)
        boundary_layerEIndex = rhinoutils.create_layer(
            act_planning, "BOUNDARY ELEVATED", (237, 0, 194, 255), elevated_layerIndex)
        building_layer_EIndex = rhinoutils.create_layer(
            act_planning, "BUILDINGS ELEVATED", (99, 99, 99, 255), elevated_layerIndex)
        topography_layerIndex = rhinoutils.create_layer(
            act_planning, "TOPOGRAPHY", (191, 191, 191, 255), elevated_layerIndex)
        contours_layer_EIndex = rhinoutils.create_layer(
            act_planning, "CONTOURS ELEVATED", (191, 191, 191, 255), elevated_layerIndex)

        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.act_boundary_url: params,
            urls.act_adminboundaries_url: params,
            urls.act_zoning_url: topo_params,
            urls.act_topo_url: topo_params,
            urls.act_heritage_url: params
        }

        urls_list = [
            urls.act_boundary_url,
            urls.act_adminboundaries_url,
            urls.act_zoning_url,
            urls.act_topo_url,
            urls.act_heritage_url
        ]

        data_dict = {}

        with imports.cf.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(
                datafetcher.get_data, url, params=params_dict[url]): url for url in urls_list}

            for future in imports.cf.as_completed(future_to_url):
                url = future_to_url[future]
                data = future.result()
                if data is not None:
                    if url == urls.act_adminboundaries_url:
                        data_dict['admin_data'] = data
                    elif url == urls.act_zoning_url:
                        data_dict['zoning_data'] = data
                    elif url == urls.act_boundary_url:
                        data_dict['lots_data'] = data
                    elif url == urls.act_topo_url:
                        data_dict['topography_data'] = data
                    elif url == urls.act_heritage_url:
                        data_dict['heritage_data'] = data

        admin_data = data_dict.get('admin_data')
        zoning_data = data_dict.get('zoning_data')
        lots_data = data_dict.get('lots_data')
        topography_data = data_dict.get('topography_data')
        heritage_data = data_dict.get('heritage_data')

        boundary_data = datafetcher.get_data(
            urls.act_boundary_url, boundary_params)

        # BOUNDARY
        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, act_planning)

        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'ID', act_planning)

        # Admin
        rhinoutils.add_to_model(
            admin_data, admin_layerIndex, 'DIVISION_NAME', act_planning)

        # Zoning
        rhinoutils.curve_to_surface(
            zoning_data, zoning_layerIndex, 'LAND_USE_ZONE_CODE_ID', 'LAND_USE_ZONE_CODE_ID', act_planning, dicts.act_zoning_dict)

        # Heritage
        rhinoutils.add_to_model(
            heritage_data, heritage_layerIndex, 'NAME', act_planning)

        # Native
        rhinoutils.add_native(urls.native_url, native_post, native_layerIndex,
                              act_planning, transformer=globals.transformer2)

        # Roads
        rhinoutils.add_roads_to_model(tiles, zoom,
                                      road_layerIndex, act_planning, transformer=globals.transformer2)

        # Isochrone
        longitude_iso = lon
        latitude_iso = lat

        iso_url_w = f'https://api.mapbox.com/isochrone/v1/{globals.profile1}/{longitude_iso}, { latitude_iso}?contours_minutes=5&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_c = f'https://api.mapbox.com/isochrone/v1/{globals.profile2}/{longitude_iso}, { latitude_iso}?contours_minutes=10&polygons=true&access_token={globals.mapbox_access_token}'

        iso_url_d = f'https://api.mapbox.com/isochrone/v1/{globals.profile3}/{longitude_iso}, {latitude_iso}?contours_minutes=15&polygons=true&access_token={globals.mapbox_access_token}'

        iso_response_w = imports.requests.get(iso_url_w)
        walking_data = imports.json.loads(iso_response_w.content.decode())

        iso_response_c = imports.requests.get(iso_url_c)
        cycling_data = imports.json.loads(iso_response_c.content.decode())

        iso_response_d = imports.requests.get(iso_url_d)
        driving_data = imports.json.loads(iso_response_d.content.decode())

        # Walking Curves
        rhinoutils.add_isochrone_to_model(
            walking_data, walking_layerIndex, act_planning, transformer=globals.transformer2)

        # Cycling Curves
        rhinoutils.add_isochrone_to_model(
            cycling_data, cycling_layerIndex, act_planning, transformer=globals.transformer2)

        # Driving Curves
        rhinoutils.add_isochrone_to_model(
            driving_data, driving_layerIndex, act_planning, transformer=globals.transformer2)

        # ras_tiles = list(imports.mercantile.tiles(ras_xmin_LL, ras_ymin_LL,
        #                                           ras_xmax_LL, ras_ymax_LL, zooms=16))

        # rhinoutils.add_raster(ras_tiles, zoom, gh_raster_decoded,
        #                       raster_layerIndex, act_planning, transformer=globals.transformer2)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, act_planning, transformer=globals.transformer2)

        # topography
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, act_planning, 'Contour')

        # giraffe
        if 'giraffeInput' in request.files:
            giraffe_file = request.files['giraffeInput']
            rhinoutils.giraffe(giraffe_file, act_planning,
                               transformer=globals.transformer2)
        else:
            pass

        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'Contour', contours_layer_EIndex,
                                                  act_planning, globals.transformer2, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex,
                                      bound_curve, gh_buildings_elevated_decoded, act_planning, globals.transformer2, mesh_geo_list)

        cen_x, cen_y = globals.transformer2.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(
            -centroid.X, -centroid.Y, -centroid.Z)

        for obj in act_planning.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)

        filename = "act_planning.3dm"
        file_path = imports.os.path.abspath(
            imports.os.path.join('tmp', 'files', filename))
        act_planning.Write(file_path, 7)
        return send_file(file_path, as_attachment=True)

    @application.route('/speckleSend', methods=['GET', 'POST'])
    def speckleSend():
        address = request.args.get('address')
        params = {
            "text": address,
            "f": "json",
            "outFields": "Location"
        }
        response = requests.get(urls.arcgis_geocoder_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "locations" in data and len(data["locations"]) > 0:
                location = data["locations"][0]
                lon = location["feature"]["geometry"]["x"]
                lat = location["feature"]["geometry"]["y"]
            else:
                return imports.jsonify(error="There is something wrong with your address, please try a different one.")

        xmin_LL, xmax_LL, ymin_LL, ymax_LL = geoutils.create_boundary(
            lat, lon, 10000)
        t_xmin_LL, t_xmax_LL, t_ymin_LL, t_ymax_LL = geoutils.create_boundary(
            lat, lon, 30000)
        boundary_params = gisparameters.create_parameters(
            f'{lon},{lat}', 'esriGeometryPoint', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', xmin_LL, ymin_LL, xmax_LL, ymax_LL, '32756')
        topo_params = gisparameters.create_parameters(
            '', 'esriGeometryEnvelope', t_xmin_LL, t_ymin_LL, t_xmax_LL, t_ymax_LL, '32756')

        tiles = list(imports.mercantile.tiles(
            xmin_LL, ymin_LL, xmax_LL, ymax_LL, zooms=16))
        zoom = 16

        speckle_model = imports.rh.File3dm()
        speckle_model.Settings.ModelUnitSystem = imports.rh.UnitSystem.Meters

        boundary_layerIndex = rhinoutils.create_layer(
            speckle_model, "BOUNDARY", (237, 0, 194, 255))
        lots_layerIndex = rhinoutils.create_layer(
            speckle_model, "LOTS", (255, 106, 0, 255))
        road_layerIndex = rhinoutils.create_layer(
            speckle_model, "ROADS", (145, 145, 145, 255))
        building_layerIndex = rhinoutils.create_layer(
            speckle_model, "BUILDINGS", (99, 99, 99, 255))
        contours_layerIndex = rhinoutils.create_layer(
            speckle_model, "CONTOURS", (191, 191, 191, 255))
        topography_layerIndex = rhinoutils.create_layer(
            speckle_model, "TOPOGRAPHY", (191, 191, 191, 255))
        contours_layer_EIndex = rhinoutils.create_layer(
            speckle_model, "CONTOURS ELEVATED", (191, 191, 191, 255))
        building_layer_EIndex = rhinoutils.create_layer(
            speckle_model, "BUILDINGS ELEVATED", (191, 191, 191, 255))
        boundary_layerEIndex = rhinoutils.create_layer(
            speckle_model, "BOUNDARY ELEVATED", (191, 191, 191, 255))

        gh_topography_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/topography.ghx")
        gh_buildings_elevated_decoded = geoutils.encode_ghx_file(
            r"./gh_scripts/elevate_buildings.ghx")

        params_dict = {
            urls.nsw_lots_url: params,
            urls.nsw_topo_url: topo_params,
        }
        urls_list = [
            urls.nsw_lots_url,
            urls.nsw_topo_url,
        ]
        data_dict = {}

        with imports.cf.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(
                datafetcher.get_data, url, params=params_dict[url]): url for url in urls_list}

            for future in imports.cf.as_completed(future_to_url):
                url = future_to_url[future]
                data = future.result()
                if data is not None:
                    if url == urls.nsw_lots_url:
                        data_dict['lots_data'] = data
                    elif url == urls.nsw_topo_url:
                        data_dict['topography_data'] = data

        lots_data = data_dict.get('lots_data')
        topography_data = data_dict.get('topography_data')

        boundary_data = datafetcher.get_data(
            urls.nsw_boundary_url, boundary_params)

        bound_curve = rhinoutils.add_boundary(
            boundary_data, boundary_layerIndex, address, speckle_model)

        # buildings
        mapboxfetcher.mapbox_buildings(
            tiles, zoom, building_layerIndex, speckle_model, transformer=globals.transformer2)

        # contours
        rhinoutils.add_contours(
            topography_data, contours_layerIndex, speckle_model, 'elevation')

        # topography
        mesh_geo_list = mapboxfetcher.mapbox_topo(topography_data, 'elevation', contours_layer_EIndex,
                                                  speckle_model, globals.transformer2, lon, lat, gh_topography_decoded, topography_layerIndex)

        mapboxfetcher.mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex,
                                      bound_curve, gh_buildings_elevated_decoded, speckle_model, globals.transformer2, mesh_geo_list)

        # lots
        rhinoutils.add_to_model(lots_data, lots_layerIndex,
                                'plannumber', speckle_model)

        cen_x, cen_y = globals.transformer2.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)

        translation_vector = imports.rh.Vector3d(-centroid.X, -
                                                 centroid.Y, -centroid.Z)

        if bound_curve is not None:
            bound_curve.Translate(translation_vector)

        for obj in speckle_model.Objects:
            if obj.Geometry != bound_curve and obj.Geometry is not None:
                obj.Geometry.Translate(translation_vector)

        filename = "speckle.3dm"
        speckle_model.Write('tmp\\files\\' + str(filename), 7)

        streamName = request.form.get('address')
        client = imports.SpeckleClient(host="https://app.speckle.systems/")
        account = imports.get_account_from_token(
            token=globals.speckleToken, server_url="https://app.speckle.systems/")
        client.authenticate_with_account(account)
        new_stream_id = client.stream.create(name=f'{streamName}')

        file_path = 'tmp\\files\\' + filename

        rhinoutils.speckle(file_path, new_stream_id)

        stream_url = 'https://app.speckle.systems/projects/' + \
            str(new_stream_id)

        imports.session['stream_url'] = stream_url

        return redirect(stream_url)

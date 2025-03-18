from planning import imports, globals


class _RhinoUtils__Rhino3dmEncoder(imports.json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "Encode"):
            return o.Encode()
        return imports.json.JSONEncoder.default(self, o)


class GeoUtils:
    @staticmethod
    def create_boundary(lat, lon, distance):
        R = 6371.0
        lat_r = imports.radians(lat)
        ns_dist = distance / (R * 1000)
        ew_dist = distance / (R * 1000 * imports.cos(lat_r))
        max_lat = lat + ns_dist
        min_lat = lat - ns_dist
        max_lon = lon + ew_dist
        min_lon = lon - ew_dist
        return min_lon, max_lon, min_lat, max_lat

    @staticmethod
    def encode_ghx_file(file_path):
        with open(file_path, mode="r", encoding="utf-8-sig") as file:
            gh_contents = file.read()
            gh_bytes = gh_contents.encode("utf-8")
            gh_encoded = imports.base64.b64encode(gh_bytes)
            gh_decoded = gh_encoded.decode("utf-8")
        return gh_decoded


class GISParameters:
    @staticmethod
    def create_parameters(geometry, geometry_type, xmin_LL, ymin_LL, xmax_LL, ymax_LL, outSR):
        params = {
            'where': '1=1',
            'geometry': f'{geometry}',
            'geometryType': f'{geometry_type}',
            'spatialRel': 'esriSpatialRelIntersects',
            'returnGeometry': 'true',
            'f': 'json',
            'outFields': '*',
            'inSR': '4326',
            'outSR': outSR
        }
        if geometry_type == 'esriGeometryEnvelope':
            params['geometry'] = f'{xmin_LL}, {ymin_LL}, {xmax_LL}, {ymax_LL}'
        return params


class ComputeAPI:
    @staticmethod
    def send_compute_post(payload):
        retries = imports.Retry(
            total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        session = imports.requests.Session()
        session.mount('http://', imports.HTTPAdapter(max_retries=retries))

        for _ in range(3):
            try:
                res = session.post(
                    globals.compute_url + "grasshopper", json=payload, headers=globals.headers)
                res.raise_for_status()  # This will raise an exception for HTTP errors
                return res
            except imports.requests.exceptions.RequestException as e:
                error_message = str(e)

        # If we've exhausted all retries, return an error response
        return imports.jsonify(error=error_message), 500


class MapboxFetcher:
    @staticmethod
    def fetch_mapbox_data(zoom, tile):
        mb_url = f"https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/{zoom}/{
            tile.x}/{tile.y}.mvt?access_token={globals.mapbox_access_token}"
        counter = 0
        while True:
            try:
                mb_response = imports.requests.get(mb_url)
                mb_response.raise_for_status()
                mb_data = mb_response.content
                return mb_data
            except imports.requests.exceptions.RequestException as e:
                counter += 1
                if counter >= 3:
                    error_message = e
                    return imports.jsonify(error=error_message)
                imports.time.sleep(0)

    @staticmethod
    def concurrent_fetching(zoom, tile):
        with imports.cf.ThreadPoolExecutor() as executor:
            future = executor.submit(
                MapboxFetcher.fetch_mapbox_data, zoom, tile)
            result = future.result()
        return result

    @staticmethod
    def mapbox_buildings(tiles, zoom, building_layerIndex, model, transformer):
        def process_geometry(geometry, height):
            for ring in geometry:
                points = []
                for coord in ring:
                    x_val, y_val = coord[0], coord[1]
                    x_prop = (x_val / 4096)
                    y_prop = (y_val / 4096)
                    lon_delta = lon2 - lon1
                    lat_delta = lat2 - lat1
                    lon_mapped = lon1 + (x_prop * lon_delta)
                    lat_mapped = lat1 + (y_prop * lat_delta)
                    lon_mapped, lat_mapped = transformer.transform(
                        lon_mapped, lat_mapped)
                    point = imports.rh.Point3d(lon_mapped, lat_mapped, 0)
                    points.append(point)
                polyline = imports.rh.Polyline(points)
                curve = polyline.ToNurbsCurve()
                orientation = curve.ClosedCurveOrientation()
                if orientation == imports.rh.CurveOrientation.Clockwise:
                    curve.Reverse()
                extrusion = imports.rh.Extrusion.Create(curve, height, True)
                att = imports.rh.ObjectAttributes()
                att.LayerIndex = building_layerIndex
                att.SetUserString("Building Height", str(height))
                model.Objects.AddExtrusion(extrusion, att)

        for tile in tiles:
            mb_data = MapboxFetcher.concurrent_fetching(zoom, tile)
            tiles1 = imports.mapbox_vector_tile.decode(mb_data)
            building_layerMB = tiles1.get('building', {'features': []})
            tile1 = imports.mercantile.Tile(tile.x, tile.y, 16)
            bbox = imports.mercantile.bounds(tile1)
            lon1, lat1, lon2, lat2 = bbox

            for feature in building_layerMB['features']:
                geometry_type = feature['geometry']['type']
                height = feature['properties']['height']

                if geometry_type == 'Polygon':
                    geometry = feature['geometry']['coordinates']
                    process_geometry(geometry, height)
                elif geometry_type == 'MultiPolygon':
                    geometry = feature['geometry']['coordinates']
                    for polygon in geometry:
                        process_geometry(polygon, height)

    @staticmethod
    def mapbox_topo(topography_data, p_key, contours_layer_EIndex, model, transformer, lon, lat, algo, topography_layerIndex):
        terrain_curves = []
        terrain_elevations = []
        if "features" in topography_data:
            for feature in topography_data["features"]:
                elevation = feature['attributes'][p_key]
                geometry = feature["geometry"]

                for ring in geometry["paths"]:
                    points = []
                    points_e = []

                    for coord in ring:
                        point = imports.rh.Point3d(coord[0], coord[1], 0)
                        point_e = imports.rh.Point3d(
                            coord[0], coord[1], elevation)
                        points.append(point)
                        points_e.append(point_e)

                    polyline = imports.rh.Polyline(points)
                    polyline_e = imports.rh.Polyline(points_e)
                    curve = polyline.ToNurbsCurve()
                    curve_e = polyline_e.ToNurbsCurve()

                    terrain_curves.append(curve)
                    terrain_elevations.append(int(elevation))

                    att = imports.rh.ObjectAttributes()
                    att.LayerIndex = contours_layer_EIndex
                    att.SetUserString("Elevation", str(elevation))
                    model.Objects.AddCurve(curve_e, att)

        mesh_geo_list = []
        curves_list_terrain = [{"ParamName": "Curves", "InnerTree": {}}]

        for i, curve in enumerate(terrain_curves):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            curves_list_terrain[0]["InnerTree"][key] = value

        elevations_list_terrain = [
            {"ParamName": "Elevations", "InnerTree": {}}]
        for i, elevation in enumerate(terrain_elevations):
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "System.Int32",
                    "data": elevation
                }
            ]
            elevations_list_terrain[0]["InnerTree"][key] = value

        centre_list = []
        cen_x, cen_y = transformer.transform(lon, lat)
        centroid = imports.rh.Point3d(cen_x, cen_y, 0)
        centre_list.append(centroid)

        centre_point_list = [{"ParamName": "Point", "InnerTree": {}}]
        for i, point in enumerate(centre_list):
            serialized_point = imports.json.dumps(
                point, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Point",
                    "data": serialized_point
                }
            ]
            centre_point_list[0]["InnerTree"][key] = value

        geo_payload = {
            "algo": algo,
            "pointer": None,
            "values": curves_list_terrain + elevations_list_terrain + centre_point_list
        }

        res = ComputeAPI.send_compute_post(geo_payload)
        response_object = imports.json.loads(res.content)['values']
        for val in response_object:
            paramName = val['ParamName']
            innerTree = val['InnerTree']
            for key, innerVals in innerTree.items():
                for innerVal in innerVals:
                    if 'data' in innerVal:
                        data = imports.json.loads(innerVal['data'])
                        mesh_geo = imports.rh.CommonObject.Decode(data)
                        mesh_geo_list.append(mesh_geo)
                        att = imports.rh.ObjectAttributes()
                        att.LayerIndex = topography_layerIndex
                        model.Objects.AddMesh(mesh_geo, att)
        return mesh_geo_list

    @staticmethod
    def mapbox_elevated(tiles, zoom, building_layer_EIndex, boundary_layerEIndex, bound_curve, elevated_algo, model, transformer, mesh_geo_list):
        def process_geometry(geometry, height):
            nonlocal buildings
            for ring in geometry:
                points = []
                for coord in ring:
                    x_val, y_val = coord[0], coord[1]
                    x_prop = (x_val / 4096)
                    y_prop = (y_val / 4096)
                    lon_delta = lon2 - lon1
                    lat_delta = lat2 - lat1
                    lon_mapped = lon1 + (x_prop * lon_delta)
                    lat_mapped = lat1 + (y_prop * lat_delta)
                    lon_mapped, lat_mapped = transformer.transform(
                        lon_mapped, lat_mapped)
                    point = imports.rh.Point3d(lon_mapped, lat_mapped, 0)
                    points.append(point)
                polyline = imports.rh.Polyline(points)
                curve = polyline.ToNurbsCurve()
                orientation = curve.ClosedCurveOrientation()
                if orientation == imports.rh.CurveOrientation.Clockwise:
                    curve.Reverse()
                extrusion = imports.rh.Extrusion.Create(curve, height, True)
                buildings.append(extrusion)

        buildings = []
        for tile in tiles:
            mb_data = MapboxFetcher.concurrent_fetching(zoom, tile)
            tiles1 = imports.mapbox_vector_tile.decode(mb_data)

            if 'building' in tiles1:
                building_layerMB = tiles1['building']
                tile1 = imports.mercantile.Tile(tile.x, tile.y, zoom)
                bbox = imports.mercantile.bounds(tile1)
                lon1, lat1, lon2, lat2 = bbox

                for feature in building_layerMB['features']:
                    geometry_type = feature['geometry']['type']
                    height = feature['properties']['height']

                    if geometry_type == 'Polygon':
                        geometry = feature['geometry']['coordinates']
                        process_geometry(geometry, height)
                    elif geometry_type == 'MultiPolygon':
                        geometry = feature['geometry']['coordinates']
                        for polygon in geometry:
                            for ring in polygon:
                                process_geometry([ring], height)

        buildings_elevated = [
            {"ParamName": "Buildings", "InnerTree": {}}]

        for i, brep in enumerate(buildings):
            serialized_extrusion = imports.json.dumps(
                brep, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Extrusion",
                    "data": serialized_extrusion
                }
            ]
            buildings_elevated[0]["InnerTree"][key] = value

        mesh_terrain = [{"ParamName": "Mesh", "InnerTree": {}}]
        for i, mesh in enumerate(mesh_geo_list):
            serialized = imports.json.dumps(
                mesh, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Mesh",
                    "data": serialized
                }
            ]
            mesh_terrain[0]["InnerTree"][key] = value

        boundcurves_list = []
        boundcurves_list.append(bound_curve)

        bound_curves = [{"ParamName": "Boundary", "InnerTree": {}}]
        for i, curve in enumerate(boundcurves_list):
            serialized = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized
                }
            ]
            bound_curves[0]["InnerTree"][key] = value

        geo_payload = {
            "algo": elevated_algo,
            "pointer": None,
            "values": buildings_elevated + mesh_terrain + bound_curves
        }

        res = ComputeAPI.send_compute_post(geo_payload)
        response_object = imports.json.loads(res.content)['values']
        for val in response_object:
            paramName = val['ParamName']
            if paramName == 'RH_OUT:Elevated':
                innerTree = val['InnerTree']
                for key, innerVals in innerTree.items():
                    for innerVal in innerVals:
                        if 'data' in innerVal:
                            data = imports.json.loads(innerVal['data'])
                            geo = imports.rh.CommonObject.Decode(data)
                            att = imports.rh.ObjectAttributes()
                            att.LayerIndex = building_layer_EIndex
                            model.Objects.AddExtrusion(geo, att)
            elif paramName == 'RH_OUT:UpBound':
                innerTree = val['InnerTree']
                for key, innerVals in innerTree.items():
                    for innerVal in innerVals:
                        if 'data' in innerVal:
                            data = imports.json.loads(innerVal['data'])
                            geo = imports.rh.CommonObject.Decode(data)
                            att = imports.rh.ObjectAttributes()
                            att.LayerIndex = boundary_layerEIndex
                            model.Objects.AddCurve(geo, att)


class DataFetcher:
    @staticmethod
    def get_data(url, params):
        while True:
            try:
                response = imports.requests.get(url, params, timeout=5)
                data = imports.json.loads(response.text)
                return data
            except (imports.RequestException, imports.Timeout) as e:
                imports.time.sleep(0)

    def get_paginated_data(self, url, params):
        """
        Fetches paginated data from ArcGIS REST API by handling the 1000 record limit
        """
        all_features = []
        params['resultOffset'] = 0

        while True:
            response = imports.requests.get(url, params=params)
            if response.status_code != 200:
                print(f"Error fetching data: {response.status_code}")
                return None

            data = imports.json.loads(response.text)

            if 'features' not in data:
                print(f"No features found in response: {data}")
                break

            features = data['features']
            if not features:
                break

            all_features.extend(features)

            # Check if we've received all records
            if len(features) < 1000:  # Less than max means we've got all records
                break

            # Update offset for next batch
            params['resultOffset'] += 1000

        # Construct final response with all features
        if all_features:
            return {
                'features': all_features,
                'geometryType': data.get('geometryType'),
                'spatialReference': data.get('spatialReference')
            }
        return None


class RhinoUtils:
    @staticmethod
    def serialize(brep):
        serialized = imports.json.dumps(brep, cls=_RhinoUtils__Rhino3dmEncoder)
        return serialized

    @staticmethod
    def create_layer(model, name, color, parent_id=None):
        layer = imports.rh.Layer()

        # If parent exists, set the name with the parent path
        if parent_id is not None:
            parent_layer = model.Layers[parent_id]
            if parent_layer:
                layer.Name = name
                layer.ParentLayerId = parent_layer.Id
        else:
            layer.Name = name

        layer.Color = color
        return model.Layers.Add(layer)

    @staticmethod
    def add_to_model(data, layer_index, attribute_key, model):
        if data.get("features") is not None:
            for feature in data["features"]:
                attribute_value = feature['attributes'][attribute_key]
                geometry = feature["geometry"]
                for ring in geometry["rings"]:
                    points = [imports.rh.Point3d(
                        coord[0], coord[1], 0) for coord in ring]
                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()
                    att = imports.rh.ObjectAttributes()
                    att.LayerIndex = layer_index
                    att.SetUserString(attribute_key, str(attribute_value))
                    model.Objects.AddCurve(curve, att)

    @staticmethod
    def add_aiport(data, layer_index, model):
        if data.get("features") is not None:
            for feature in data["features"]:
                min_height = feature['attributes']['MINIMUM_HEIGHT']
                geometry = feature["geometry"]
                for ring in geometry["rings"]:
                    points = []
                    for coord in ring:
                        point = imports.rh.Point3d(
                            coord[0], coord[1], min_height)
                        points.append(point)
                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()
                    att = imports.rh.ObjectAttributes()
                    att.LayerIndex = layer_index
                    att.SetUserString(
                        "Minimum Height", str(min_height))
                    model.Objects.AddCurve(
                        curve, att)

    @staticmethod
    def add_surface_to_model(data, layerIndex, p_key, paramName, gh_algo, model):
        curves = []
        numbers = []

        if data.get("features") is not None:
            for feature in data["features"]:
                num = feature['attributes'][str(p_key)]
                if num is None:
                    continue
                geometry = feature["geometry"]
                for ring in geometry["rings"]:
                    points = []
                    for coord in ring:
                        point = imports.rh.Point3d(coord[0], coord[1], 0)
                        points.append(point)
                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()
                    curves.append(curve)
                    numbers.append(str(num))

        curves_data = [{"ParamName": "Curves", "InnerTree": {}}]

        for i, curve in enumerate(curves):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            curves_data[0]["InnerTree"][key] = value

        names_data = [{"ParamName": paramName, "InnerTree": {}}]
        for i, number in enumerate(numbers):
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "System.String",
                    "data": number
                }
            ]
            names_data[0]["InnerTree"][key] = value

        geo_payload = {
            "algo": gh_algo,
            "pointer": None,
            "values": curves_data + names_data
        }

        res = ComputeAPI.send_compute_post(geo_payload)
        response_object = imports.json.loads(res.content)['values']

        colors = []
        surfaces = []
        string_vals = []

        for val in response_object:
            paramName = val['ParamName']
            innerTree = val.get('InnerTree', {})
            for _, innerVals in innerTree.items():
                for innerVal in innerVals:
                    if 'data' in innerVal:
                        data = imports.json.loads(innerVal['data'])
                        if paramName == "RH_OUT:Colors":
                            colors.append(data)
                        elif paramName == "RH_OUT:Surface":
                            geo = imports.rh.CommonObject.Decode(data)
                            surfaces.append(geo)
                        elif paramName == "RH_OUT:Values":
                            string_vals.append(data)

        for idx, (color, geo) in enumerate(zip(colors, surfaces)):
            r, g, b = map(int, color.split(','))
            att = imports.rh.ObjectAttributes()
            a = 255
            att.ColorSource = imports.rh.ObjectColorSource.ColorFromObject
            att.LayerIndex = layerIndex
            att.SetUserString(p_key, str(string_vals[idx]))
            att.ObjectColor = (r, g, b, int(a))
            model.Objects.AddBrep(geo, att)

    @staticmethod
    def add_roads_to_model(tiles, zoom, road_layerIndex, model, transformer):
        def process_geometry(geometry):
            points_list = []
            for ring in geometry:
                x_val, y_val = ring[0], ring[1]
                x_prop = (x_val / 4096)
                y_prop = (y_val / 4096)
                lon_delta = lon2 - lon1
                lat_delta = lat2 - lat1
                lon_mapped = lon1 + (x_prop * lon_delta)
                lat_mapped = lat1 + (y_prop * lat_delta)
                lon_mapped, lat_mapped = transformer.transform(
                    lon_mapped, lat_mapped)
                point = imports.rh.Point3d(lon_mapped, lat_mapped, 0)
                points_list.append(point)
            polyline = imports.rh.Polyline(points_list)
            curve = polyline.ToNurbsCurve()
            road_curves.append(curve)

        road_curves = []
        for tile in tiles:
            mb_data = MapboxFetcher.concurrent_fetching(zoom, tile)
            tiles1 = imports.mapbox_vector_tile.decode(mb_data)

            if 'road' not in tiles1:
                continue

            road_layer = tiles1['road']

            tile1 = imports.mercantile.Tile(tile.x, tile.y, 16)
            bbox = imports.mercantile.bounds(tile1)
            lon1, lat1, lon2, lat2 = bbox

            for feature in road_layer['features']:
                geometry_type = feature['geometry']['type']
                if geometry_type == 'LineString':
                    geometry = feature['geometry']['coordinates']
                    process_geometry(geometry)
                elif geometry_type == 'MultiLineString':
                    geometry = feature['geometry']['coordinates']
                    for line_string in geometry:
                        process_geometry(line_string)

        # Add road curves directly to model
        for curve in road_curves:
            att = imports.rh.ObjectAttributes()
            att.LayerIndex = road_layerIndex
            model.Objects.AddCurve(curve, att)

    @staticmethod
    def add_isochrone_to_model(data, layerIndex, model, transformer):
        for feature in data['features']:
            geometry_type = feature['geometry']['type']
            if geometry_type == 'Polygon':
                geometry = feature['geometry']['coordinates']
                for ring in geometry:
                    points = []
                    for coord in ring:
                        iso_x, iso_y = coord[0], coord[1]
                        iso_x, iso_y = transformer.transform(iso_x, iso_y)
                        point = imports.rh.Point3d(iso_x, iso_y, 0)
                        points.append(point)
                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()
                    att = imports.rh.ObjectAttributes()
                    att.LayerIndex = layerIndex
                    model.Objects.AddCurve(curve, att)

    @staticmethod
    def add_nsw_zoning_to_model(data, algo, layerIndex, model):
        curves = []
        names = []
        for feature in data["features"]:
            zoning_name = feature['attributes']['SYM_CODE']
            geometry = feature["geometry"]
            points = []
            for coord in geometry["rings"][0]:
                point = imports.rh.Point3d(coord[0], coord[1], 0)
                points.append(point)
            polyline = imports.rh.Polyline(points)
            curve = polyline.ToNurbsCurve()
            curves.append(curve)
            names.append(zoning_name)

        curves_zoning = [{"ParamName": "Curves", "InnerTree": {}}]
        for i, curve in enumerate(curves):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            curves_zoning[0]["InnerTree"][key] = value

        names_zoning = [{"ParamName": "Zoning", "InnerTree": {}}]
        for i, zone in enumerate(names):
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "System.String",
                    "data": zone
                }
            ]
            names_zoning[0]["InnerTree"][key] = value
        geo_payload = {
            "algo": algo,
            "pointer": None,
            "values": curves_zoning + names_zoning
        }

        res = imports.requests.post(globals.compute_url + "grasshopper",
                                    json=geo_payload, headers=globals.headers)
        response_object = imports.json.loads(res.content)['values']

        colors = []
        surfaces = []
        string_vals = []

        for val in response_object:
            paramName = val['ParamName']
            innerTree = val.get('InnerTree', {})
            for _, innerVals in innerTree.items():
                for innerVal in innerVals:
                    if 'data' in innerVal:
                        data = imports.json.loads(innerVal['data'])
                        if paramName == "RH_OUT:Colors":
                            colors.append(data)
                        elif paramName == "RH_OUT:Surface":
                            geo = imports.rh.CommonObject.Decode(data)
                            surfaces.append(geo)
                        elif paramName == "RH_OUT:Values":
                            string_vals.append(data)

        for idx, (color, geo) in enumerate(zip(colors, surfaces)):
            r, g, b, a = map(int, color.split(','))
            att = imports.rh.ObjectAttributes()
            att.ColorSource = imports.rh.ObjectColorSource.ColorFromObject
            att.LayerIndex = layerIndex
            att.SetUserString("Zoning Code", str(string_vals[idx]))
            att.ObjectColor = (r, g, b, a)
            model.Objects.AddBrep(geo, att)

    @staticmethod
    def add_raster(ras_tiles, zoom, algo, layerIndex, model, transformer):
        for tile in ras_tiles:
            mb_url = f"https://api.mapbox.com/v4/mapbox.satellite/{zoom}/{tile.x}/{
                tile.y}@2x.png256?access_token={globals.mapbox_access_token}"
            response = imports.requests.get(mb_url)

            if response.status_code == 200:
                image_data = imports.BytesIO(response.content)
                image = imports.Image.open(image_data)
                file_name = "ras.png"
                image.save('planning\\tmp\\' + file_name)

        rastile = ras_tiles[0]

        bbox = imports.mercantile.bounds(rastile)
        lon1, lat1, lon2, lat2 = bbox
        t_lon1, t_lat1 = transformer.transform(lon1, lat1)
        t_lon2, t_lat2 = transformer.transform(lon2, lat2)

        raster_points = [
            imports.rh.Point3d(t_lon1, t_lat1, 0),
            imports.rh.Point3d(t_lon2, t_lat1, 0),
            imports.rh.Point3d(t_lon2, t_lat2, 0),
            imports.rh.Point3d(t_lon1, t_lat2, 0),
            imports.rh.Point3d(t_lon1, t_lat1, 0)
        ]

        points_list = imports.rh.Point3dList(raster_points)
        raster_curve = imports.rh.PolylineCurve(points_list)
        raster_curve = raster_curve.ToNurbsCurve()

        with open('planning\\tmp\\' + file_name, 'rb') as img_file:
            img_bytes = img_file.read()

        b64_string = imports.base64.b64encode(img_bytes).decode('utf-8')

        string_encoded = b64_string
        send_string = [{"ParamName": "BaseString", "InnerTree": {}}]

        serialized_string = imports.json.dumps(
            string_encoded, cls=_RhinoUtils__Rhino3dmEncoder)
        key = "{0};0".format(0)
        value = [
            {
                "type": "System.String",
                "data": serialized_string
            }
        ]
        send_string[0]["InnerTree"][key] = value

        curve_payload = [{"ParamName": "Curve", "InnerTree": {}}]
        serialized_curve = imports.json.dumps(
            raster_curve, cls=_RhinoUtils__Rhino3dmEncoder)
        key = "{0};0".format(0)
        value = [
            {
                "type": "Rhino.Geometry.Curve",
                "data": serialized_curve
            }
        ]
        curve_payload[0]["InnerTree"][key] = value

        geo_payload = {
            "algo": algo,
            "pointer": None,
            "values": send_string + curve_payload
        }

        res = ComputeAPI.send_compute_post(geo_payload)
        response_object = imports.json.loads(res.content)['values']

        for val in response_object:
            innerTree = val['InnerTree']
            for key, innerVals in innerTree.items():
                for innerVal in innerVals:
                    if 'data' in innerVal:
                        data = imports.json.loads(innerVal['data'])
                        geo = imports.rh.CommonObject.Decode(data)
                        att = imports.rh.ObjectAttributes()
                        att.LayerIndex = layerIndex
                        model.Objects.AddMesh(geo, att)

    @staticmethod
    def add_native(native_url, native_post, layerIndex, model, transformer):
        native_response = imports.requests.post(native_url, json=native_post)
        native_data = native_response.json()
        for feature in native_data:
            geometry = feature['geometry']
            properties = feature['properties']
            name = properties['Name']
            for ring in geometry['coordinates']:
                points = []
                for coord in ring:
                    native_x, native_y = transformer.transform(
                        coord[0], coord[1])
                    point = imports.rh.Point3d(native_x, native_y, 0)
                    points.append(point)
                polyline = imports.rh.Polyline(points)
                curve = polyline.ToNurbsCurve()
                att = imports.rh.ObjectAttributes()
                att.LayerIndex = layerIndex
                att.SetUserString("Native Name", str(name))
                model.Objects.AddCurve(curve, att)

    @staticmethod
    def add_boundary(data, layerIndex, address, model):
        if data.get("features") is not None:
            for feature in data["features"]:
                geometry = feature["geometry"]
                for ring in geometry["rings"]:
                    points = []
                    for coord in ring:
                        point = imports.rh.Point3d(coord[0], coord[1], 0)
                        points.append(point)
                    polyline = imports.rh.Polyline(points)
                    bound_curve = polyline.ToNurbsCurve()
                    att = imports.rh.ObjectAttributes()
                    att.LayerIndex = layerIndex
                    att.SetUserString("Address", str(address))
                    model.Objects.AddCurve(bound_curve, att)
        return bound_curve

    @staticmethod
    def add_contours(data, layerIndex, model, p_key):
        for feature in data["features"]:
            elevation = feature['attributes'][str(p_key)]
            geometry = feature["geometry"]
            for ring in geometry["paths"]:
                points = []
                for coord in ring:
                    point = imports.rh.Point3d(
                        coord[0], coord[1], 0)
                    points.append(point)
                polyline = imports.rh.Polyline(points)
                curve = polyline.ToNurbsCurve()
                att = imports.rh.ObjectAttributes()
                att.LayerIndex = layerIndex
                att.SetUserString(
                    "Elevation", str(elevation))
                model.Objects.AddCurve(curve, att)

    @staticmethod
    def giraffe(giraffe_file, model, transformer):
        sub_layers = {}
        giraffe_file_path = 'planning\\tmp\\files\\' + giraffe_file.filename
        giraffe_file.save(giraffe_file_path)
        with open(giraffe_file_path) as f:
            data = imports.json.load(f)
        for feature in data['features']:
            geometry_type = feature.get('geometry', {}).get('type')
            layer_id = feature.get('properties', {}).get('layerId')
            usage = feature.get('properties', {}).get('usage')
            if geometry_type == 'Point':
                x, y = feature['geometry']['coordinates']
                x, y = transformer.transform(x, y)
                circle_center = imports.rh.Point3d(x, y, 0)
                circle_radius = 1.0
                circle = imports.rh.Circle(circle_center, circle_radius)

                extrusion = imports.rh.Extrusion.Create(
                    circle.ToNurbsCurve(), 10, True)

                top_point = imports.rh.Point3d(x, y, 10)
                sphere = imports.rh.Sphere(top_point, 2.5)

                if layer_id is None:
                    continue

                if layer_id not in sub_layers:
                    sub_layer_name = f"Giraffe:{layer_id}"
                    sub_layer = imports.rh.Layer()
                    sub_layer.Name = sub_layer_name
                    sub_layers[layer_id] = model.Layers.Add(
                        sub_layer)

                att = imports.rh.ObjectAttributes()
                att.LayerIndex = sub_layers[layer_id]
                att.SetUserString("Usage", str(usage))
                model.Objects.AddExtrusion(extrusion, att)
                model.Objects.AddSphere(sphere, att)

            elif geometry_type == 'Polygon':
                layer_id = feature['properties'].get('layerId')
                if layer_id is None:
                    continue

                if layer_id not in sub_layers:
                    sub_layer_name = f"Giraffe:{layer_id}"
                    sub_layer = imports.rh.Layer()
                    sub_layer.Name = sub_layer_name
                    sub_layers[layer_id] = model.Layers.Add(
                        sub_layer)

                geometry = feature.get(
                    'geometry', {}).get('coordinates')
                height = feature.get(
                    'properties', {}).get('_height')
                base_height = feature.get(
                    'properties', {}).get('_baseHeight')
                usage = feature.get('properties', {}).get('usage')

                if base_height == 0 and height == 0:
                    for ring in geometry:
                        points = []
                        for coord in ring:
                            x, y = transformer.transform(
                                coord[0], coord[1])
                            point = imports.rh.Point3d(x, y, 0)
                            points.append(point)
                        polyline = imports.rh.Polyline(points)
                        curve = polyline.ToNurbsCurve()
                        att = imports.rh.ObjectAttributes()
                        att.SetUserString("Usage", str(usage))
                        att.LayerIndex = sub_layers[layer_id]
                        model.Objects.AddCurve(curve, att)

                for ring in geometry:
                    points = []
                    for coord in ring:
                        x, y = transformer.transform(
                            coord[0], coord[1])
                        point = imports.rh.Point3d(x, y, base_height)
                        points.append(point)

                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()
                    extrusion_height = height - base_height
                    extrusion = imports.rh.Extrusion.Create(
                        curve, extrusion_height, True)

                    att = imports.rh.ObjectAttributes()
                    att.SetUserString("Usage", str(usage))
                    att.LayerIndex = sub_layers[layer_id]
                    model.Objects.AddExtrusion(
                        extrusion, att)

    @staticmethod
    def speckle(file_path, new_stream_id):
        imports.rhFile = imports.rh.File3dm.Read(file_path)
        layers = imports.rhFile.Layers

        topo = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Topography":
                topo.append(obj)

        topo_meshes = [obj.Geometry for obj in topo]

        topo_to_send = [{"ParamName": "Mesh", "InnerTree": {}}]

        for i, mesh in enumerate(topo_meshes):
            serialized_mesh = imports.json.dumps(
                mesh, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Mesh",
                    "data": serialized_mesh
                }
            ]
            topo_to_send[0]["InnerTree"][key] = value

        buildings = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Buildings":
                buildings.append(obj)

        buildings_list = [obj.Geometry for obj in buildings]

        buildings_to_send = [{"ParamName": "Buildings", "InnerTree": {}}]

        for i, brep in enumerate(buildings_list):
            serialized_brep = imports.json.dumps(
                brep, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Brep",
                    "data": serialized_brep
                }
            ]
            buildings_to_send[0]["InnerTree"][key] = value

        elevated_buildings = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Buildings Elevated":
                elevated_buildings.append(obj)

        elevated_buildings_list = [obj.Geometry for obj in elevated_buildings]

        elevated_buildings_to_send = [
            {"ParamName": "ElevatedBuildings", "InnerTree": {}}]

        for i, brep in enumerate(elevated_buildings_list):
            serialized_brep = imports.json.dumps(
                brep, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Brep",
                    "data": serialized_brep
                }
            ]
            elevated_buildings_to_send[0]["InnerTree"][key] = value

        contours = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Contours":
                contours.append(obj)

        contours_list = [obj.Geometry for obj in contours]

        contours_to_send = [{"ParamName": "Contours", "InnerTree": {}}]

        for i, curve in enumerate(contours_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            contours_to_send[0]["InnerTree"][key] = value

        roads = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Roads":
                roads.append(obj)

        roads_list = [obj.Geometry for obj in roads]

        roads_to_send = [{"ParamName": "Roads", "InnerTree": {}}]

        for i, curve in enumerate(roads_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            roads_to_send[0]["InnerTree"][key] = value

        lots = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Lots":
                lots.append(obj)

        lots_list = [obj.Geometry for obj in lots]

        lots_to_send = [{"ParamName": "Lots", "InnerTree": {}}]

        for i, curve in enumerate(lots_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            lots_to_send[0]["InnerTree"][key] = value

        isochrones = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Walking Isochrone" or layers[layer_index].Name == "Cycling Isochrone" or layers[layer_index].Name == "Driving Isochrone":
                isochrones.append(obj)

        isochrones_list = [obj.Geometry for obj in isochrones]

        isochrones_to_send = [{"ParamName": "Isochrone", "InnerTree": {}}]

        for i, curve in enumerate(isochrones_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            isochrones_to_send[0]["InnerTree"][key] = value

        parks = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Parks":
                parks.append(obj)

        parks_list = [obj.Geometry for obj in parks]

        parks_to_send = [{"ParamName": "Parks", "InnerTree": {}}]

        for i, curve in enumerate(parks_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            parks_to_send[0]["InnerTree"][key] = value

        heritage = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Heritage":
                heritage.append(obj)

        heritage_list = [obj.Geometry for obj in heritage]

        heritage_to_send = [{"ParamName": "Heritage", "InnerTree": {}}]

        for i, curve in enumerate(heritage_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            heritage_to_send[0]["InnerTree"][key] = value

        flood = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Flood":
                flood.append(obj)

        flood_list = [obj.Geometry for obj in flood]

        flood_to_send = [{"ParamName": "Flood", "InnerTree": {}}]

        for i, curve in enumerate(flood_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            flood_to_send[0]["InnerTree"][key] = value

        native = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Native Land":
                native.append(obj)

        native_list = [obj.Geometry for obj in native]

        native_to_send = [{"ParamName": "Native", "InnerTree": {}}]

        for i, curve in enumerate(native_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            native_to_send[0]["InnerTree"][key] = value

        admin = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Administrative Boundaries":
                admin.append(obj)

        admin_list = [obj.Geometry for obj in admin]

        admin_to_send = [{"ParamName": "Admin", "InnerTree": {}}]

        for i, curve in enumerate(admin_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            admin_to_send[0]["InnerTree"][key] = value

        bushfire = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Bushfire":
                bushfire.append(obj)

        bushfire_list = [obj.Geometry for obj in bushfire]

        bushfire_to_send = [{"ParamName": "Bushfire", "InnerTree": {}}]

        for i, curve in enumerate(bushfire_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            bushfire_to_send[0]["InnerTree"][key] = value

        boundary = []
        for obj in imports.rhFile.Objects:
            layer_index = obj.Attributes.LayerIndex
            if layers[layer_index].Name == "Boundary":
                boundary.append(obj)

        boundary_list = [obj.Geometry for obj in boundary]

        boundary_to_send = [{"ParamName": "Boundary", "InnerTree": {}}]

        for i, curve in enumerate(boundary_list):
            serialized_curve = imports.json.dumps(
                curve, cls=_RhinoUtils__Rhino3dmEncoder)
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "Rhino.Geometry.Curve",
                    "data": serialized_curve
                }
            ]
            boundary_to_send[0]["InnerTree"][key] = value

        input_streams = []
        input_streams.append(new_stream_id)

        url_to_send = [{"ParamName": "StreamID", "InnerTree": {}}]

        for i, url in enumerate(input_streams):
            key = f"{{{i};0}}"
            value = [
                {
                    "type": "System.String",
                    "data": url
                }
            ]
            url_to_send[0]["InnerTree"][key] = value

        gh_decoded = GeoUtils.encode_ghx_file(
            r'planning\gh_scripts\topoSpeckle.ghx')

        geo_payload = {
            "algo": gh_decoded,
            "pointer": None,
            "values": topo_to_send + url_to_send + buildings_to_send + elevated_buildings_to_send + contours_to_send + roads_to_send + lots_to_send + isochrones_to_send + parks_to_send + heritage_to_send + flood_to_send + admin_to_send + native_to_send + bushfire_to_send + boundary_to_send
        }

        ComputeAPI.send_compute_post(geo_payload)

    @staticmethod
    def get_bottom_face(brep, tol=1e-6):
        bottom_face = None
        min_z = None
        for face in brep.Faces:
            bbox = face.GetBoundingBox()
            if abs(bbox.Min.Z - bbox.Max.Z) < tol:
                if min_z is None or bbox.Min.Z < min_z:
                    min_z = bbox.Min.Z
                    bottom_face = face
        return bottom_face

    @staticmethod
    def curve_to_surface(data, layer_index, dict_key, attribute_key, model, color_dict):
        if data.get("features") is not None:
            # Create a list to store features with their areas
            features_with_areas = []
            processed_codes = {}  # Track processed SYM_CODEs and their ring counts

            # First pass: calculate areas and store valid features
            for feature in data["features"]:
                attribute_value = feature['attributes'].get(attribute_key)
                if attribute_value is None:
                    continue

                # Calculate total area for all valid rings in this feature
                total_area = 0
                geometry = feature["geometry"]
                valid_rings = []

                # Only process the first ring if we've seen this SYM_CODE before
                sym_code = feature['attributes'].get('SYM_CODE')
                if sym_code in processed_codes:
                    # If this feature has multiple rings, only take the largest one
                    if len(geometry["rings"]) > 1:
                        # Find the ring with the largest area
                        max_area = 0
                        largest_ring = None
                        for ring in geometry["rings"]:
                            points = [imports.rh.Point3d(
                                coord[0], coord[1], 0) for coord in ring]
                            if len(points) < 3:
                                continue
                            polyline = imports.rh.Polyline(points)
                            curve = polyline.ToNurbsCurve()
                            if curve and curve.IsValid:
                                bbox = curve.GetBoundingBox()
                                area = abs((bbox.Max.X - bbox.Min.X)
                                           * (bbox.Max.Y - bbox.Min.Y))
                                if area > max_area:
                                    max_area = area
                                    largest_ring = ring
                        if largest_ring:
                            valid_rings = [largest_ring]
                    else:
                        valid_rings = geometry["rings"]
                else:
                    processed_codes[sym_code] = True
                    valid_rings = geometry["rings"]

                for ring in valid_rings:
                    points = [imports.rh.Point3d(
                        coord[0], coord[1], 0) for coord in ring]
                    if len(points) < 3:
                        continue

                    polyline = imports.rh.Polyline(points)
                    curve = polyline.ToNurbsCurve()

                    if curve and curve.IsValid:
                        bbox = curve.GetBoundingBox()
                        if bbox:
                            area = abs((bbox.Max.X - bbox.Min.X)
                                       * (bbox.Max.Y - bbox.Min.Y))
                            if area > 0:
                                total_area += area

                # Only add feature if it has valid rings
                if valid_rings:
                    feature["geometry"]["rings"] = valid_rings
                    features_with_areas.append((total_area, feature))

            # Sort features by area in descending order (largest first)
            features_with_areas.sort(reverse=True, key=lambda x: x[0])
            total_features = len(features_with_areas)

            # Second pass: create surfaces in order of decreasing area
            for i, (_, feature) in enumerate(features_with_areas):
                z_offset = -((total_features - 1 - i) * 0.01)
                dict_value = feature['attributes'].get(dict_key)
                attribute_value = feature['attributes'].get(attribute_key)
                color_list = color_dict.get(dict_value)

                for ring in feature["geometry"]["rings"]:
                    try:
                        points = [imports.rh.Point3d(
                            coord[0], coord[1], z_offset) for coord in ring]
                        polyline = imports.rh.Polyline(points)
                        curve = polyline.ToNurbsCurve()

                        if curve and curve.IsValid:
                            extrusion = imports.rh.Extrusion.Create(
                                curve, 1, True)
                            if extrusion:
                                brep = extrusion.ToBrep(True)
                                if brep:
                                    bottom_face = RhinoUtils.get_bottom_face(
                                        brep)
                                    if bottom_face:
                                        surface = bottom_face.DuplicateFace(
                                            True)
                                        if surface:
                                            att = imports.rh.ObjectAttributes()
                                            att.ColorSource = imports.rh.ObjectColorSource.ColorFromObject
                                            if color_list is not None:
                                                r, g, b, a = color_list
                                                att.ObjectColor = (r, g, b, a)
                                            else:
                                                att.ObjectColor = (
                                                    128, 128, 128, 255)
                                            att.SetUserString(
                                                attribute_key, str(attribute_value))
                                            att.LayerIndex = layer_index
                                            model.Objects.AddBrep(surface, att)
                    except Exception:
                        continue
        else:
            pass

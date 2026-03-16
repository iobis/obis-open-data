import json
import boto3
import botocore
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
import logging
from io import BytesIO
import pyarrow as pa
import pyarrow.parquet as pq


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class STACCreator:
    def __init__(self):
        self.s3_bucket = "obis-open-data"
        self.s3_prefix = "occurrence/"
        self.keywords = ["biodiversity", "marine", "ocean", "OBIS"]
        self.license = "CC BY-NC 4.0"
        self.providers = [
            {
                "name": "Ocean Biodiversity Information System (OBIS)",
                "description": "Ocean Biodiversity Information System (OBIS)",
                "roles": ["producer", "licensor", "processor", "host"],
                "url": "https://obis.org"
            },
            {
                "name": "UNESCO-IOC",
                "description": "Intergovernmental Oceanographic Commission of UNESCO",
                "roles": ["producer", "licensor", "processor", "host"],
                "url": "https://ioc.unesco.org"
            }
        ]
        self.extent = {
            "spatial": {
                "bbox": [[-180, -90, 180, 90]]
            },
            "temporal": {
                "interval": [[None, "2025-12-31T23:59:59Z"]]
            }
        }
        self.s3_client = boto3.client("s3", config=boto3.session.Config(signature_version=botocore.UNSIGNED))
    
    def _find_first_parquet_key(self) -> str:
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.s3_bucket, Prefix=self.s3_prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".parquet"):
                    return obj["Key"]
        return ""

    def _arrow_type_to_table_type(self, arrow_type: pa.DataType) -> str:
        if pa.types.is_boolean(arrow_type):
            return "boolean"
        if pa.types.is_integer(arrow_type):
            return "integer"
        if pa.types.is_floating(arrow_type) or pa.types.is_decimal(arrow_type):
            return "number"
        if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
            return "string"
        if pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
            return "binary"
        if pa.types.is_timestamp(arrow_type) or pa.types.is_date(arrow_type):
            return "string"
        if pa.types.is_struct(arrow_type):
            return "struct"
        if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
            return "list"
        if pa.types.is_map(arrow_type):
            return "map"
        return str(arrow_type)

    def _flatten_schema_fields(self, parent: str, field: pa.Field) -> List[Dict[str, Any]]:
        name = f"{parent}.{field.name}" if parent else field.name
        entries: List[Dict[str, Any]] = []
        entries.append({
            "name": name,
            "type": self._arrow_type_to_table_type(field.type)
        })
        if pa.types.is_struct(field.type):
            for child in field.type:
                entries.extend(self._flatten_schema_fields(name, child))
        elif pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
            value_field = field.type.value_field
            entries.extend(self._flatten_schema_fields(name, value_field))
        elif pa.types.is_map(field.type):
            key_field = field.type.key_field
            item_field = field.type.item_field
            entries.extend(self._flatten_schema_fields(name + ".key", key_field))
            entries.extend(self._flatten_schema_fields(name + ".value", item_field))
        return entries

    def generate_table_columns_from_s3_parquet(self) -> Tuple[List[Dict[str, Any]], str]:
        parquet_key = self._find_first_parquet_key()
        logger.info(f"Reading schema from s3://{self.s3_bucket}/{parquet_key}")
        obj = self.s3_client.get_object(Bucket=self.s3_bucket, Key=parquet_key)
        data = obj["Body"].read()
        pf = pq.ParquetFile(BytesIO(data))
        schema: pa.Schema = pf.schema_arrow
        columns: List[Dict[str, Any]] = []
        for field in schema:
            columns.extend(self._flatten_schema_fields("", field))
        return (columns, parquet_key)
    
    def create_catalog_json(self) -> Dict[str, Any]:
        return {
            "stac_version": "1.0.0",
            "type": "Catalog",
            "id": "obis-open-data-catalog",
            "title": "OBIS open data catalog",
            "description": "OBIS open data catalog",
            # "keywords": self.keywords,
            # "license": self.license,
            # "providers": self.providers,
            # "extent": self.extent,
            "links": [
                {
                    "rel": "root",
                    "href": "./catalog.json",
                    "type": "application/json",
                    "title": "Root catalog"
                },
                {
                    "rel": "child",
                    "href": "./obis-open-data-occurrence-collection/collection.json",
                    "type": "application/json",
                    "title": "OBIS open data occurrence collection"
                },
                {
                    "rel": "self",
                    "href": "./catalog.json",
                    "type": "application/json"
                }
            ]
        }
    
    def create_collection_json(self) -> Dict[str, Any]:
        return {
            "stac_version": "1.0.0",
            "type": "Collection",
            "id": "obis-open-data-occurrence-collection",
            "title": "OBIS open data occurrence collection",
            "description": "OBIS open data occurrence collection",
            "keywords": self.keywords,
            "license": self.license,
            "providers": self.providers,
            "extent": self.extent,
            "sci:citation": "Ocean Biodiversity Information System (OBIS) (25 March 2025) OBIS Occurrence Data. Intergovernmental Oceanographic Commission of UNESCO. https://doi.org/10.25607/obis.occurrence.b89117cd",
            "sci:doi": "10.25607/obis.occurrence.b89117cd",
            "item_assets": {
                "data": {
                    "type": "application/x-parquet",
                    "roles": ["data"],
                    "title": "GeoParquet file",
                    "description": "GeoParquet file"
                }
            },
            # "properties": {
            #     "sci:citation": "Ocean Biodiversity Information System (OBIS) (25 March 2025) OBIS Occurrence Data. Intergovernmental Oceanographic Commission of UNESCO. https://doi.org/10.25607/obis.occurrence.b89117cd",
            #     "sci:doi": "10.25607/obis.occurrence.b89117cd",
            #     "created": datetime.utcnow().isoformat() + "Z",
            #     "updated": datetime.utcnow().isoformat() + "Z"
            # },
            "links": [
                {
                    "rel": "root",
                    "href": "../catalog.json",
                    "type": "application/json",
                    "title": "Root catalog"
                },
                {
                    "rel": "parent",
                    "href": "../catalog.json",
                    "type": "application/json",
                    "title": "Parent catalog"
                },
                {
                    "rel": "self",
                    "href": "./collection.json",
                    "type": "application/json"
                },
                {
                    "rel": "license",
                    "href": "https://creativecommons.org/licenses/by-nc/4.0/",
                    "type": "text/html",
                    "title": "CC BY-NC 4.0 License"
                },
                {
                    "rel": "documentation",
                    "href": "https://github.com/iobis/obis-open-data",
                    "type": "text/html",
                    "title": "Dataset documentation"
                }
            ],
            "stac_extensions": [
                "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                "https://stac-extensions.github.io/item-assets/v1.0.0/schema.json"
            ]
        }
    
    def create_item_json(self) -> Dict[str, Any]:
        return {
            "stac_version": "1.0.0",
            "type": "Feature",
            "id": "obis-open-data-occurrence-geoparquet",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [self.extent["spatial"]["bbox"][0][0], self.extent["spatial"]["bbox"][0][1]],
                    [self.extent["spatial"]["bbox"][0][2], self.extent["spatial"]["bbox"][0][1]],
                    [self.extent["spatial"]["bbox"][0][2], self.extent["spatial"]["bbox"][0][3]],
                    [self.extent["spatial"]["bbox"][0][0], self.extent["spatial"]["bbox"][0][3]],
                    [self.extent["spatial"]["bbox"][0][0], self.extent["spatial"]["bbox"][0][1]]
                ]]
            },
            "bbox": self.extent["spatial"]["bbox"][0],
            "properties": {
                "datetime": None,
                "start_datetime": self.extent["temporal"]["interval"][0][0],
                "end_datetime": self.extent["temporal"]["interval"][0][1],
                "title": "OBIS occurrence dataset as GeoParquet",
                "description": "OBIS occurrence dataset as GeoParquet",
                "created": datetime.utcnow().isoformat() + "Z",
                "updated": datetime.utcnow().isoformat() + "Z",
                "sci:citation": "Ocean Biodiversity Information System (OBIS) (25 March 2025) OBIS Occurrence Data. Intergovernmental Oceanographic Commission of UNESCO. https://doi.org/10.25607/obis.occurrence.b89117cd",
                "sci:doi": "10.25607/obis.occurrence.b89117cd",
                "table:columns": []
            },
            "assets": {
                "data": {
                    "href": f"s3://{self.s3_bucket}/occurrence/*",
                    "type": "application/x-parquet",
                    "roles": ["data"],
                    "title": "GeoParquet file",
                    "description": "Geoparquet file"
                }
            },
            "collection": "obis-open-data-occurrence-collection",
            "links": [
                {
                    "rel": "collection",
                    "href": "../collection.json",
                    "type": "application/json",
                    "title": "Parent collection"
                },
                {
                    "rel": "parent",
                    "href": "../collection.json",
                    "type": "application/json",
                    "title": "Parent collection"
                },
                {
                    "rel": "root",
                    "href": "../../catalog.json",
                    "type": "application/json",
                    "title": "Root catalog"
                },
                {
                    "rel": "self",
                    "href": f"./obis-occurrence-geoparquet.json",
                    "type": "application/json"
                }
            ],
            "stac_extensions": [
                "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                "https://stac-extensions.github.io/table/v1.2.0/schema.json",
                "https://stac-extensions.github.io/file/v2.0.0/schema.json"
            ]
        }
    
    def create_full_catalog(self, output_dir: str):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        collection_dir = output_path / "obis-open-data-occurrence-collection"
        collection_dir.mkdir(exist_ok=True)
        items_dir = collection_dir / "items"
        items_dir.mkdir(exist_ok=True)
        
        catalog_json = self.create_catalog_json()
        with open(output_path / "catalog.json", "w") as f:
            json.dump(catalog_json, f, indent=2)
        
        collection_json = self.create_collection_json()
        
        item_json = self.create_item_json()
        # item_json["properties"]["title"] = "OBIS Occurrence Dataset"
        # item_json["properties"]["description"] = "Marine biodiversity occurrence data from OBIS (entire dataset)"
        # item_json["assets"]["data"]["href"] = f"s3://{self.s3_bucket}/{self.s3_prefix}"
        
        try:
            table_columns, sampled_key = self.generate_table_columns_from_s3_parquet()
            item_json["properties"]["table:columns"] = table_columns
            if sampled_key:
                item_json["assets"]["data"]["sample"] = f"s3://{self.s3_bucket}/{sampled_key}"
        except Exception as e:
            logger.warning(f"Failed to auto-generate table:columns: {e}")
                
        with open(items_dir / f"obis-occurrence-geoparquet.json", "w") as f:
            json.dump(item_json, f, indent=2)
        
        collection_json["links"].append({
            "rel": "item",
            "href": f"./items/obis-occurrence-geoparquet.json",
            "type": "application/json",
            "title": "OBIS open data occurrence dataset as GeoParquet"
        })
        
        with open(collection_dir / "collection.json", "w") as f:
            json.dump(collection_json, f, indent=2)
        
        logger.info(f"STAC catalog created at {output_path}")
        logger.info("Catalog contains 1 item")
        
        return output_path


def main():
    creator = STACCreator()
    catalog_path = creator.create_full_catalog(output_dir="./stac")
    print(f"STAC catalog created at: {catalog_path}")


if __name__ == "__main__":
    main()

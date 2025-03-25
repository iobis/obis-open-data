import duckdb
import time

start_time = time.time()

query = """
    install spatial;
    load spatial;
    select
        dataset_id, _id as id,
        interpreted.*,
        source.scientificName as originalScientificName,
        flags,
        dropped,
        absence
    from read_parquet('s3://obis-open-data/occurrence/*.parquet')
    -- from read_parquet('/Users/pieter/Desktop/occurrence/*.parquet')
    where (interpreted.speciesid = 141433) 
        and (dropped is not true) 
        and (absence is not true);
"""

results = duckdb.query(query).to_df()
print(results)

end_time = time.time()
elapsed_time = end_time - start_time
print(f"Script executed in {elapsed_time:.2f} seconds")

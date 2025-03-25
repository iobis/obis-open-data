library(DBI)
library(duckdb)
library(tictoc)

con <- dbConnect(duckdb::duckdb())

tic()
df <- dbGetQuery(con, "
    select interpreted.* from read_parquet('../occurrence/*.parquet')
    where interpreted.genus == 'Abra'
")
print(dim(df))
toc()

tic()
df <- dbGetQuery(con, "
    install spatial;
    load spatial;
    select interpreted.* from read_parquet('../occurrence/*.parquet')
    where ST_Intersects(geometry, ST_GeomFromText('POLYGON ((2.831383 51.212045, 2.896957 51.212045, 2.896957 51.240211, 2.831383 51.240211, 2.831383 51.212045))'))
")
print(dim(df))
toc()

dbDisconnect(con, shutdown = TRUE)

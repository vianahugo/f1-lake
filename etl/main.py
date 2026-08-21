# %%
import os
import dotenv
import nekt

dotenv.load_dotenv()

from tqdm import tqdm

# %%
nekt.data_access_token = os.getenv["NEKT_TOKEN"]
nekt.engine = "spark"

# %%

# Custom imports
import nekt

query_dates = """
SELECT DISTINCT
    DATE(date) AS dt_ref
FROM
    f1_results
WHERE 
    YEAR(date) = '{year}'
ORDER BY
    1
"""

# Minha query de Feature Store
query = """
-- =============================================================================
-- F1 Data Lake | Feature Store: Perfil de carreira do piloto
-- Base: f1_results
-- Data de referência: Dinâmica ({date})
-- =============================================================================

WITH
  -- 1. Resultados base, limitados até a data de referência
  results_until_date AS (
    SELECT
      *
    FROM
      f1_results
    WHERE
      DATE(date) <= DATE('{date}')
    ORDER BY
      date DESC
  ),

  -- 2. Pilotos que competiram nas últimas 3 temporadas (temporada atual + 2 anteriores)
  drivers_selected AS (
    SELECT DISTINCT
      driverid
    FROM
      results_until_date
    WHERE
      YEAR >= (
        SELECT MAX(YEAR) - 2
        FROM results_until_date
      )
  ),

  -- 3. Histórico completo de resultados para os pilotos selecionados
  tb_results AS (
    SELECT
      t1.*
    FROM
      results_until_date AS t1
    INNER JOIN drivers_selected AS t2 
      ON t1.driverid = t2.driverid
    ORDER BY
      YEAR
  ),

  -- 4. Métricas de carreira agregadas por piloto
  tb_life AS (
    SELECT
      driverid,

      -- Participação
      COUNT(DISTINCT YEAR)                                                        AS qtd_seasons,
      COUNT(*)                                                                    AS qtd_sessions,
      SUM(CASE WHEN mode = 'Race'   THEN 1 ELSE 0 END)                            AS qtd_race,
      SUM(CASE WHEN mode = 'Sprint' THEN 1 ELSE 0 END)                            AS qtd_sprint,

      -- Finishes (status = 'Finished' ou volta perdida)
      SUM(CASE WHEN status = 'Finished' OR status LIKE '+%' THEN 1 ELSE 0 END)                AS qtde_sessions_finished,
      SUM(CASE WHEN mode = 'Race'   AND (status = 'Finished' OR status LIKE '+%') THEN 1 ELSE 0 END) AS qtde_sessions_finished_race,
      SUM(CASE WHEN mode = 'Sprint' AND (status = 'Finished' OR status LIKE '+%') THEN 1 ELSE 0 END) AS qtde_sessions_finished_sprint,

      -- Vitórias (P1)
      SUM(CASE WHEN POSITION = 1 THEN 1 ELSE 0 END)                               AS qtde_1Pos,
      SUM(CASE WHEN POSITION = 1 AND MODE = 'Race'   THEN 1 ELSE 0 END)           AS qtde_1Pos_race,
      SUM(CASE WHEN POSITION = 1 AND MODE = 'Sprint' THEN 1 ELSE 0 END)           AS qtde_1Pos_sprint,

      -- Pódios (P1-P3)
      SUM(CASE WHEN POSITION <= 3 THEN 1 ELSE 0 END)                              AS qtde_podios,
      SUM(CASE WHEN POSITION <= 3 AND mode = 'Race'   THEN 1 ELSE 0 END)          AS qtde_podios_race,
      SUM(CASE WHEN POSITION <= 3 AND mode = 'Sprint' THEN 1 ELSE 0 END)          AS qtde_podios_sprint,

      -- Top 5 (chegada)
      SUM(CASE WHEN POSITION <= 5 THEN 1 ELSE 0 END)                              AS qtde_pos5,
      SUM(CASE WHEN POSITION <= 5 AND mode = 'Race'   THEN 1 ELSE 0 END)          AS qtde_pos5_race,
      SUM(CASE WHEN POSITION <= 5 AND mode = 'Sprint' THEN 1 ELSE 0 END)          AS qtde_pos5_sprint,

      -- Top 5 no grid (largada)
      SUM(CASE WHEN gridposition <= 5 THEN 1 ELSE 0 END)                           AS qtde_gridpos5,
      SUM(CASE WHEN gridposition <= 5 AND mode = 'Race'   THEN 1 ELSE 0 END)       AS qtde_gridpos5_race,
      SUM(CASE WHEN gridposition <= 5 AND mode = 'Sprint' THEN 1 ELSE 0 END)       AS qtde_gridpos5_sprint,

      -- Pontos
      SUM(points)                                                                 AS qtde_points,
      SUM(CASE WHEN mode = 'Race'   THEN points END)                              AS qtde_points_race,
      SUM(CASE WHEN mode = 'Sprint' THEN points END)                              AS qtde_points_sprint,
      SUM(CASE WHEN points > 0 THEN 1 ELSE 0 END)                                 AS qtd_sessions_with_points,
      SUM(CASE WHEN mode = 'Race'   AND points > 0 THEN 1 ELSE 0 END)             AS qtd_sessions_with_points_race,
      SUM(CASE WHEN mode = 'Sprint' AND points > 0 THEN 1 ELSE 0 END)             AS qtd_sessions_with_points_sprint,

      -- Posição média de largada (grid)
      AVG(gridposition)                                                           AS avg_gridposition,
      AVG(CASE WHEN mode = 'Race'   THEN gridposition END)                        AS avg_gridposition_race,
      AVG(CASE WHEN mode = 'Sprint' THEN gridposition END)                        AS avg_gridposition_sprint,

      -- Posição média de chegada
      AVG(POSITION)                                                               AS avg_position,
      AVG(CASE WHEN mode = 'Race'   THEN POSITION END)                            AS avg_position_race,
      AVG(CASE WHEN mode = 'Sprint' THEN POSITION END)                            AS avg_position_sprint,

      -- Pole positions (grid = 1)
      SUM(CASE WHEN gridposition = 1 THEN 1 ELSE 0 END)                            AS qtde_1_gridposition,
      SUM(CASE WHEN gridposition = 1 AND mode = 'Race'   THEN 1 ELSE 0 END)        AS qtde_1_gridposition_race,
      SUM(CASE WHEN gridposition = 1 AND mode = 'Sprint' THEN 1 ELSE 0 END)        AS qtde_1_gridposition_sprint,

      -- Conversão pole -> vitória (largou em P1 e terminou em P1)
      SUM(CASE WHEN gridposition = 1 AND POSITION = 1 THEN 1 ELSE 0 END)          AS qtde_pole_win,
      SUM(CASE WHEN gridposition = 1 AND POSITION = 1 AND mode = 'Race'   THEN 1 ELSE 0 END)    AS qtde_pole_win_race,
      SUM(CASE WHEN gridposition = 1 AND POSITION = 1 AND mode = 'Sprint' THEN 1 ELSE 0 END)    AS qtde_pole_win_sprint,

      -- Ultrapassagens (posições ganhas em relação ao grid)
      SUM(CASE WHEN POSITION < gridPOSITION THEN 1 ELSE 0 END)                     AS qtde_sessions_with_overtake,
      SUM(CASE WHEN mode = 'Race'   AND POSITION < gridPOSITION THEN 1 ELSE 0 END)   AS qtde_sessions_with_overtake_race,
      SUM(CASE WHEN mode = 'Sprint' AND POSITION < gridPOSITION THEN 1 ELSE 0 END)   AS qtde_sessions_with_overtake_sprint,
      AVG(gridPOSITION - POSITION)                                                AS avg_overtake,
      AVG(CASE WHEN mode = 'Race'   THEN gridPOSITION - POSITION END)             AS avg_overtake_race,
      AVG(CASE WHEN mode = 'Sprint' THEN gridPOSITION - POSITION END)             AS avg_overtake_sprint

    FROM
      tb_results
    GROUP BY
      driverid
  )

SELECT
  DATE('{date}') AS dt_ref,
  *
FROM
  tb_life
ORDER BY
  driverid
"""

# Carregamento das tabelas necessárias para a query
(nekt.load_table(layer_name="Bronze", table_name="f1_results")
     .createOrReplaceTempView("f1_results"))


# Sessão spark
spark = nekt.get_spark_session()

years = list(range(1991, 2025))

for y in years:

    dates = (spark.sql(query_dates.format(year=y))
                  .toPandas()["dt_ref"]
                  .astype(str)
                  .tolist())
    
    if not dates:
        continue

    df_all = spark.sql(query.format(date=dates.pop(0)))

    for dt in tqdm(dates):
        df_all = df_all.union(spark.sql(query.format(date=dt)))

    # Salva dataframe resultante da query
    nekt.save_table(
        df=df_all,
        layer_name="Silver",
        table_name="fs_f1_driver_life",
        folder_name="f1",
    )

    del(df_all)

# %%
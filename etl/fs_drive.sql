-- =============================================================================
-- F1 Data Lake | Perfil de carreira do piloto (janela móvel de 3 temporadas)
-- Base: f1_data_lake_bronze.f1_results
-- Data de referência: 2024-04-21
-- =============================================================================

WITH

  -- 1. Resultados base, limitados até a data de referência
  results_until_date AS (
    SELECT
      *
    FROM
      `f1_data_lake_bronze`.`f1_results`
    WHERE
      DATE(date) <= DATE('2024-04-21')
  ),

  -- 2. Pilotos que competiram nas últimas 3 temporadas (temporada atual + 2 anteriores)
  drivers_selected AS (
    SELECT DISTINCT
      driverid
    FROM
      results_until_date
    WHERE
      year >= (
        SELECT MAX(year) - 2
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
  ),

  -- 4. Métricas de carreira agregadas por piloto
  tb_life AS (
    SELECT
      driverid,

      -- Participação
      COUNT(DISTINCT year)                                                        AS qtde_seasons,
      COUNT(*)                                                                    AS qtde_sessions,
      SUM(CASE WHEN mode = 'Race'   THEN 1 ELSE 0 END)                            AS qtde_race,
      SUM(CASE WHEN mode = 'Sprint' THEN 1 ELSE 0 END)                            AS qtde_sprint,

      -- Finishes (status = 'Finished' ou volta perdida, ex.: '+1 Lap')
      SUM(CASE WHEN status = 'Finished' OR status LIKE '+%' THEN 1 ELSE 0 END)                AS qtde_sessions_finished,
      SUM(CASE WHEN mode = 'Race'   AND (status = 'Finished' OR status LIKE '+%') THEN 1 ELSE 0 END) AS qtde_sessions_finished_race,
      SUM(CASE WHEN mode = 'Sprint' AND (status = 'Finished' OR status LIKE '+%') THEN 1 ELSE 0 END) AS qtde_sessions_finished_sprint,

      -- Vitórias (P1)
      SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END)                               AS qtde_1pos,
      SUM(CASE WHEN position = 1 AND mode = 'Race'   THEN 1 ELSE 0 END)           AS qtde_1pos_race,
      SUM(CASE WHEN position = 1 AND mode = 'Sprint' THEN 1 ELSE 0 END)           AS qtde_1pos_sprint,

      -- Pódios (P1-P3)
      SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END)                              AS qtde_podios,
      SUM(CASE WHEN position <= 3 AND mode = 'Race'   THEN 1 ELSE 0 END)          AS qtde_podios_race,
      SUM(CASE WHEN position <= 3 AND mode = 'Sprint' THEN 1 ELSE 0 END)          AS qtde_podios_sprint,

      -- Top 5 (chegada)
      SUM(CASE WHEN position <= 5 THEN 1 ELSE 0 END)                              AS qtde_pos5,
      SUM(CASE WHEN position <= 5 AND mode = 'Race'   THEN 1 ELSE 0 END)          AS qtde_pos5_race,
      SUM(CASE WHEN position <= 5 AND mode = 'Sprint' THEN 1 ELSE 0 END)          AS qtde_pos5_sprint,

      -- Pontos
      SUM(points)                                                                 AS qtde_points,
      SUM(CASE WHEN mode = 'Race'   THEN points END)                              AS qtde_points_race,
      SUM(CASE WHEN mode = 'Sprint' THEN points END)                              AS qtde_points_sprint,
      SUM(CASE WHEN points > 0 THEN 1 ELSE 0 END)                                 AS qtd_sessions_with_points,
      SUM(CASE WHEN mode = 'Race'   AND points > 0 THEN 1 ELSE 0 END)             AS qtd_sessions_with_points_race,
      SUM(CASE WHEN mode = 'Sprint' AND points > 0 THEN 1 ELSE 0 END)             AS qtd_sessions_with_points_sprint,

      -- Posição média de chegada
      AVG(position)                                                               AS avg_position,
      AVG(CASE WHEN mode = 'Race'   THEN position END)                            AS avg_position_race,
      AVG(CASE WHEN mode = 'Sprint' THEN position END)                            AS avg_position_sprint,

      -- Posição média de largada (grid)
      AVG(CASE WHEN mode = 'Race'   THEN gridposition END)                        AS avg_gridposition_race,
      AVG(CASE WHEN mode = 'Sprint' THEN gridposition END)                        AS avg_gridposition_sprint,

      -- Pole positions (grid = 1)
      SUM(CASE WHEN gridposition = 1 THEN 1 ELSE 0 END)                            AS qtde_1_gridposition,
      SUM(CASE WHEN gridposition = 1 AND mode = 'Race'   THEN 1 ELSE 0 END)        AS qtde_1_gridposition_race,
      SUM(CASE WHEN gridposition = 1 AND mode = 'Sprint' THEN 1 ELSE 0 END)        AS qtde_1_gridposition_sprint,

      -- Top 5 no grid (largada)
      SUM(CASE WHEN gridposition <= 5 THEN 1 ELSE 0 END)                           AS qtde_gridpos5,
      SUM(CASE WHEN gridposition <= 5 AND mode = 'Race'   THEN 1 ELSE 0 END)       AS qtde_gridpos5_race,
      SUM(CASE WHEN gridposition <= 5 AND mode = 'Sprint' THEN 1 ELSE 0 END)       AS qtde_gridpos5_sprint,

      -- Conversão pole -> vitória (largou em P1 e terminou em P1)
      SUM(CASE WHEN gridposition = 1 AND position = 1 THEN 1 ELSE 0 END)          AS qtde_pole_win,
      SUM(CASE WHEN gridposition = 1 AND position = 1 AND mode = 'Race'   THEN 1 ELSE 0 END)    AS qtde_pole_win_race,
      SUM(CASE WHEN gridposition = 1 AND position = 1 AND mode = 'Sprint' THEN 1 ELSE 0 END)    AS qtde_pole_win_sprint,

      -- Ultrapassagens (posições ganhas em relação ao grid)
      SUM(CASE WHEN position < gridposition THEN 1 ELSE 0 END)                     AS qtde_sessions_with_overtake,
      SUM(CASE WHEN mode = 'Race'   AND position < gridposition THEN 1 ELSE 0 END)   AS qtde_sessions_with_overtake_race,
      SUM(CASE WHEN mode = 'Sprint' AND position < gridposition THEN 1 ELSE 0 END)   AS qtde_sessions_with_overtake_sprint,
      AVG(gridposition - position)                                                AS avg_overtake,
      AVG(CASE WHEN mode = 'Race'   THEN gridposition - position END)             AS avg_overtake_race,
      AVG(CASE WHEN mode = 'Sprint' THEN gridposition - position END)             AS avg_overtake_sprint

    FROM
      tb_results
    GROUP BY
      driverid
  )

SELECT
  *
FROM
  tb_life
ORDER BY
  driverid
# %%
"""
Materializa o recorte de inferencia da Feature Store.

Le a fs_f1_driver_all (Silver) para as ultimas N temporadas e salva o
resultado como parquet, enviando para o S3.

Exporta o HISTORICO, nao apenas o dt_ref mais recente: e isso que permite
ao app desenhar a evolucao da probabilidade corrida a corrida. O volume
continua trivial (~3 temporadas x ~24 corridas x ~20 pilotos).

As features usadas na predicao saem da MESMA tabela que gerou a ABT de
treino. Nada e recalculado em Python, o que elimina training/serving skew.

Uso:
    python etl/export_serving.py                # 3 temporadas, envia ao S3
    python etl/export_serving.py --seasons 5    # 5 temporadas
    python etl/export_serving.py --no-upload    # gera apenas local (teste)
"""

import argparse
import os
import sys
from pathlib import Path

import dotenv
import nekt

# sender.py fica na raiz do repo, este script em etl/
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sender import Sender  # noqa: E402

dotenv.load_dotenv()

nekt.data_access_token = os.environ["NEKT_TOKEN"]
nekt.engine = "spark"

OUTPUT_PATH = REPO_ROOT / "data" / "serving_features.parquet"
BUCKET_FOLDER = "artifacts/serving"

# A fs_f1_driver_life carrega TODOS os pilotos historicos em todas as datas,
# com estatisticas congeladas. Sem o filtro de 'ativos' o app listaria ~194
# pilotos no seletor, a maioria aposentada ha decadas.
QUERY = """
WITH bounds AS (
    SELECT MAX(dt_ref) AS max_dt FROM fs_f1_driver_all
),
ativos AS (
    SELECT DISTINCT r.driverid
    FROM f1_results AS r
    CROSS JOIN bounds AS b
    WHERE YEAR(r.date) >= YEAR(b.max_dt) - ({seasons} - 1)
)
SELECT t.*
FROM fs_f1_driver_all AS t
CROSS JOIN bounds AS b
INNER JOIN ativos AS a
    ON t.driverid = a.driverid
WHERE YEAR(t.dt_ref) >= YEAR(b.max_dt) - ({seasons} - 1)
ORDER BY t.dt_ref, t.driverid
"""


def export(seasons: int = 3, upload: bool = True) -> Path:
    spark = nekt.get_spark_session()

    (nekt.load_table(layer_name="Silver", table_name="fs_f1_driver_all")
         .createOrReplaceTempView("fs_f1_driver_all"))

    (nekt.load_table(layer_name="Bronze", table_name="f1_results")
         .createOrReplaceTempView("f1_results"))

    df = spark.sql(QUERY.format(seasons=seasons)).toPandas()

    if df.empty:
        raise RuntimeError("Query retornou vazio. Verifique a fs_f1_driver_all.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)

    print(f"periodo: {df['dt_ref'].min()} -> {df['dt_ref'].max()}")
    print(f"linhas:  {len(df)} ({df['driverid'].nunique()} pilotos, "
          f"{df['dt_ref'].nunique()} datas)")
    print(f"colunas: {df.shape[1]}")

    if "fullname" in df.columns:
        fallback = (df["fullname"] == df["driverid"]).sum()
        if fallback:
            print(f"AVISO: {fallback} linhas sem nome real (usando sigla)")
    print(f"tamanho: {OUTPUT_PATH.stat().st_size / 1e6:.2f} MB")

    if upload:
        # Atencao: Sender.process_file faz os.remove() apos o upload.
        Sender(os.environ["BUCKET_NAME"], BUCKET_FOLDER).process_file(str(OUTPUT_PATH))
        print(f"enviado: s3://{os.environ['BUCKET_NAME']}/{BUCKET_FOLDER}/{OUTPUT_PATH.name}")

    return OUTPUT_PATH


# %%
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, default=3,
                        help="quantas temporadas exportar (padrao: 3)")
    parser.add_argument("--no-upload", action="store_true",
                        help="gera o parquet local sem enviar ao S3")
    args = parser.parse_args()

    export(seasons=args.seasons, upload=not args.no_upload)

# %%
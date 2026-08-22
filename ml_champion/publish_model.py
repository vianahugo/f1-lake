# %%
"""
Publica o modelo campeao do MLflow em um caminho estavel no S3.

Por que isso existe: se o app Streamlit carregasse o modelo via
'models:/f1-champion/Production', ele passaria a depender do servidor
MLflow estar de pe no momento da inferencia. Isso apenas troca a
dependencia do Flask por uma dependencia pior.

Aqui o MLflow continua sendo a ferramenta de experimentacao, mas sai do
caminho critico do app: o artefato campeao e copiado para o S3 e o
Streamlit le de la.

Uso:
    python ml_champion/publish_model.py --run-id <RUN_ID>
"""

import argparse
import os
from pathlib import Path

import boto3
import dotenv
import mlflow

dotenv.load_dotenv()

mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])

S3_PREFIX = "artifacts/models/champion"


def publish(run_id: str) -> None:
    local_dir = mlflow.artifacts.download_artifacts(
        artifact_uri=f"runs:/{run_id}/model",
        dst_path="/tmp/f1_model",
    )
    local_dir = Path(local_dir)
    print(f"baixado de MLflow: {local_dir}")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_KEY"],
        aws_secret_access_key=os.environ["AWS_SECRET_KEY"],
        region_name="us-east-2",
    )
    bucket = os.environ["BUCKET_NAME"]

    count = 0
    for path in local_dir.rglob("*"):
        if path.is_file():
            key = f"{S3_PREFIX}/{path.relative_to(local_dir).as_posix()}"
            s3.upload_file(str(path), bucket, key)
            count += 1

    print(f"{count} arquivos enviados")
    print(f"MODEL_URI = s3://{bucket}/{S3_PREFIX}")


# %%
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, help="run_id do MLflow")
    args = parser.parse_args()

    publish(args.run_id)

# %%
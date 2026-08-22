"""
F1 Lakehouse - Probabilidade de titulo por piloto.

Carrega o modelo campeao e o historico de features direto do S3 e roda a
predicao no proprio processo do Streamlit. Sem API intermediaria e sem
Spark: o recorte de inferencia tem poucos milhares de linhas.
"""

import io
import os
import re

import boto3
import dotenv
import mlflow.sklearn
import pandas as pd
import streamlit as st

dotenv.load_dotenv()

st.set_page_config(page_title="F1 Lakehouse", page_icon="🏎️", layout="wide")

ID_COLS = ["dt_ref", "driverid", "fullname", "teamname", "teamcolor"]
NAME_COL = "fullname"
COR_PADRAO = "#888888"


def cfg(chave: str) -> str:
    """Le credencial do st.secrets (Streamlit Cloud) ou do .env (local)."""
    try:
        if st.runtime.secrets._file_paths_exist():
            return st.secrets[chave]
    except Exception:
        pass

    valor = os.getenv(chave)
    if not valor:
        st.error(f"Variavel '{chave}' nao encontrada no .env nem em secrets.toml.")
        st.stop()
    return valor


def format_color(x) -> str:
    """FastF1 devolve a cor sem '#' (ex.: '3671C6')."""
    if not isinstance(x, str) or not x.strip():
        return COR_PADRAO
    x = x.strip()
    return (x if x.startswith("#") else f"#{x}").lower()


class Driver:
    """Embrulha id + rotulo para o multiselect, seguindo o padrao do
    projeto original: o widget devolve o objeto, format_func mostra o nome."""

    def __init__(self, driverid: str, label: str):
        self.driverid = driverid
        self.label = label


# --------------------------------------------------------------------------
# Carregamento (cache)
# --------------------------------------------------------------------------

@st.cache_resource(show_spinner="Carregando modelo...")
def load_model():
    """cache_resource: objeto global, carregado uma vez por processo.
    Sem isso o Streamlit recarregaria o modelo do S3 a cada clique,
    porque ele reexecuta o script inteiro em toda interacao."""
    return mlflow.sklearn.load_model(cfg("MODEL_URI"))


@st.cache_data(ttl=6 * 3600, show_spinner="Carregando features...")
def load_features() -> pd.DataFrame:
    """cache_data (nao cache_resource): DataFrame e mutavel, e o
    cache_data devolve uma copia por sessao em vez de compartilhar a
    mesma instancia entre usuarios.

    Usa boto3 em vez de s3fs: o s3fs depende do aiobotocore, que fixa uma
    versao propria de botocore e conflita com o boto3 do repo.
    """
    uri = cfg("SERVING_URI")
    match = re.match(r"s3://([^/]+)/(.+)", uri)
    if not match:
        raise ValueError(f"SERVING_URI invalido: {uri!r}. Use s3://bucket/caminho.parquet")
    bucket, key = match.groups()

    s3 = boto3.client(
        "s3",
        aws_access_key_id=cfg("AWS_KEY"),
        aws_secret_access_key=cfg("AWS_SECRET_KEY"),
    )
    buffer = io.BytesIO()
    s3.download_fileobj(bucket, key, buffer)
    buffer.seek(0)

    df = pd.read_parquet(buffer)
    df["dt_ref"] = pd.to_datetime(df["dt_ref"])
    return df


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def score(_model, df: pd.DataFrame) -> pd.DataFrame:
    """Pontua todo o historico de uma vez."""
    # feature_names_in_ garante nome E ordem exatos do treino. Nunca
    # inferir as colunas do parquet: uma coluna nova na Silver
    # reordenaria o DataFrame e o modelo prediria lixo em silencio.
    features = list(_model.feature_names_in_)

    faltando = set(features) - set(df.columns)
    if faltando:
        raise ValueError(f"Features ausentes no parquet: {sorted(faltando)}")

    presentes = [c for c in ID_COLS if c in df.columns]
    out = df[presentes].copy()
    out["prob_win"] = _model.predict_proba(df[features])[:, 1]
    out["year"] = out["dt_ref"].dt.year

    if "teamcolor" in out.columns:
        out["teamcolor"] = out["teamcolor"].apply(format_color)

    # O nome do piloto pode variar entre dt_refs; fixa o mais recente.
    if NAME_COL in out.columns:
        canonico = (out.sort_values("dt_ref")
                       .drop_duplicates("driverid", keep="last")
                       .set_index("driverid")[NAME_COL])
        out["label"] = out["driverid"].map(canonico).fillna(out["driverid"])
    else:
        out["label"] = out["driverid"]

    return out


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

def main():
    st.markdown("""
    ## F1 Lakehouse :checkered_flag:

    Probabilidade de cada piloto ser campeão da temporada, estimada a cada
    corrida a partir da Feature Store construída no lakehouse.
    """)

    try:
        model = load_model()
        features_df = load_features()
        data = score(model, features_df)
    except Exception as err:
        st.error(f"Falha ao carregar dados ou modelo: {err}")
        st.stop()

    ultima_data = data["dt_ref"].max()
    st.caption(
        f"Dados até {ultima_data:%d/%m/%Y} · "
        f"{data['driverid'].nunique()} pilotos · "
        f"{data['dt_ref'].nunique()} datas de predição"
    )

    # ---- filtros -------------------------------------------------------
    rotulos = (data.drop_duplicates("driverid")
                   .set_index("driverid")["label"].sort_values())
    drivers = [Driver(did, lab) for did, lab in rotulos.items()]

    top3 = (data[data["dt_ref"] == ultima_data]
            .nlargest(3, "prob_win")["driverid"].tolist())
    default_drivers = [d for d in drivers if d.driverid in top3]

    col_a, col_b = st.columns([3, 1])
    with col_a:
        selecionados = st.multiselect(
            "Pilotos",
            options=drivers,
            format_func=lambda d: d.label,
            default=default_drivers,
        )
    with col_b:
        anos = st.multiselect(
            "Temporada",
            options=sorted(data["year"].unique(), reverse=True),
            default=[int(data["year"].max())],
        )

    ids = [d.driverid for d in selecionados]
    filtrado = data[data["driverid"].isin(ids) & data["year"].isin(anos)]

    if filtrado.empty:
        st.info("Selecione ao menos um piloto e uma temporada.")
        st.stop()

    # ---- visualizacoes -------------------------------------------------
    pivot = (filtrado.pivot_table(index="dt_ref", columns="label",
                                  values="prob_win")
                     .reset_index())

    # Cores na MESMA ordem das colunas do pivot (nao confiar em sort implicito).
    if "teamcolor" in filtrado.columns:
        mapa_cor = (filtrado.sort_values("dt_ref")
                            .drop_duplicates("label", keep="last")
                            .set_index("label")["teamcolor"])
        cores = [mapa_cor.get(c, COR_PADRAO) for c in pivot.columns[1:]]
    else:
        cores = None

    col_cfg = {c: st.column_config.NumberColumn(c, format="percent")
               for c in pivot.columns[1:]}
    col_cfg["dt_ref"] = st.column_config.DateColumn("Data da predição")

    aba_evolucao, aba_ranking, aba_tabelas = st.tabs(
        ["Evolução", "Ranking", "Tabelas"]
    )

    with aba_evolucao:
        st.line_chart(
            pivot,
            x="dt_ref",
            y=pivot.columns.tolist()[1:],
            x_label="Data pós-corrida",
            y_label="Prob. de ser campeão",
            color=cores,
            height=460,
        )

    with aba_ranking:
        ano_rank = max(anos)
        snapshot = data[data["year"] == ano_rank]
        snapshot = snapshot[snapshot["dt_ref"] == snapshot["dt_ref"].max()]
        st.bar_chart(
            snapshot.set_index("label")["prob_win"].sort_values(ascending=False),
            height=460,
            color="#e10600",
        )
        st.caption(f"Situação em {snapshot['dt_ref'].max():%d/%m/%Y} — todos os pilotos.")

    with aba_tabelas:
        st.dataframe(pivot, column_config=col_cfg,
                     use_container_width=True, hide_index=True)

        with st.expander("Features do modelo (piloto na última data)"):
            piloto = st.selectbox("Piloto", ids)
            importancias = pd.Series(
                model.named_steps["RandomForest"].feature_importances_,
                index=model.feature_names_in_,
            ).sort_values(ascending=False).head(20)

            linha = features_df[
                (features_df["driverid"] == piloto)
                & (features_df["dt_ref"] == features_df["dt_ref"].max())
            ]
            if linha.empty:
                st.info("Piloto sem registro na data mais recente.")
            else:
                st.dataframe(
                    pd.DataFrame({
                        "importância": importancias,
                        "valor": linha[importancias.index].iloc[0],
                    }),
                    use_container_width=True,
                )

    st.caption(
        "As probabilidades são estimadas de forma independente para cada "
        "piloto e por isso não somam 100%. Leia como 'chance individual de "
        "ser campeão', não como divisão de um total."
    )


if __name__ == "__main__":
    main()
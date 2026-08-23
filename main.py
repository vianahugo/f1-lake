# %%
import datetime
import os
import time
import traceback

import dotenv

from collect import CollectResults
from sender import Sender

dotenv.load_dotenv()

BUCKET_NAME = os.environ["BUCKET_NAME"]
BUCKET_FOLDER = "f1/results"
INTERVALO_HORAS = 6

# %%


def executar_ciclo() -> None:
    """Coleta a temporada corrente e envia os parquets para a camada Raw."""
    ano = datetime.datetime.now().year

    print("Coletando dados...")
    CollectResults(years=[ano]).process_years()

    print("Enviando dados...")
    Sender(BUCKET_NAME, bucket_folder=BUCKET_FOLDER).process_folder("data/")


# %%

if __name__ == "__main__":

    while True:
        inicio = datetime.datetime.now()
        print(f"\n=== Iniciando processo em {inicio:%d/%m/%Y %H:%M:%S} ===")

        try:
            executar_ciclo()
            print("Iteracao finalizada com sucesso.")

        except KeyboardInterrupt:
            print("\nInterrompido pelo usuario.")
            break

        except Exception:
            # Falha em um ciclo nao derruba o agendador: registra e
            # aguarda a proxima janela.
            print("Iteracao falhou:")
            traceback.print_exc()

        print(f"Proxima execucao em {INTERVALO_HORAS}h.")
        time.sleep(60 * 60 * INTERVALO_HORAS)

# %%
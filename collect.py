# %%
import argparse
import time

import fastf1
import pandas as pd

pd.set_option('display.max_columns', None)

# %%


class CollectResults:
    """Coleta resultados de corridas da Formula 1 via API do FastF1.

    Para cada ano, percorre as rodadas sequencialmente ate encontrar uma
    corrida inexistente, o que indica o fim da temporada. Cada sessao e
    salva como um parquet independente na pasta data/.
    """

    MAX_ROUNDS = 40

    def __init__(self, years=(2021, 2022, 2023), modes=("R", "S"), data_dir="data"):
        # Listas, e nao conjuntos: a ordem importa. O modo "R" (corrida)
        # precisa ser avaliado antes de "S" (sprint), porque e a ausencia
        # da corrida que sinaliza o fim da temporada.
        self.years = list(years)
        self.modes = list(modes)
        self.data_dir = data_dir

    def get_data(self, year: int, gp: int, mode: str) -> pd.DataFrame:
        try:
            session = fastf1.get_session(year, gp, mode)
            session.load(laps=False, telemetry=False, weather=False, messages=False)

        except ValueError:
            # Rodada inexistente para o ano: fim esperado da temporada.
            return pd.DataFrame()

        except Exception as err:
            # Falha de rede, timeout ou mudanca de schema na origem.
            print(f"  ! {year} rodada {gp:02d} {mode}: {type(err).__name__}: {err}")
            return pd.DataFrame()

        df = session.results

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        df["Year"] = session.date.year
        df["Date"] = session.date
        df["Mode"] = session.name
        df["RoundNumber"] = session.event["RoundNumber"]
        df["OfficialEventName"] = session.event["OfficialEventName"]
        df["EventName"] = session.event["EventName"]
        df["Country"] = session.event["Country"]
        df["Location"] = session.event["Location"]

        return df

    def save_data(self, df: pd.DataFrame, year: int, gp: int, mode: str) -> str:
        filename = f"{self.data_dir}/{year}_{gp:02d}_{mode}.parquet"
        df.to_parquet(filename, index=False)
        return filename

    def process(self, year: int, gp: int, mode: str) -> bool:
        df = self.get_data(year, gp, mode)

        if df.empty:
            return False

        self.save_data(df, year, gp, mode)
        time.sleep(1)
        return True

    def process_year_modes(self, year: int) -> int:
        salvos = 0

        for rodada in range(1, self.MAX_ROUNDS + 1):
            for mode in self.modes:
                ok = self.process(year, rodada, mode)
                salvos += int(ok)

                # Sem corrida nesta rodada: a temporada terminou.
                if not ok and mode == "R":
                    return salvos

        return salvos

    def process_years(self) -> int:
        total = 0

        for year in self.years:
            print(f"Coletando dados do ano {year}")
            salvos = self.process_year_modes(year)
            print(f"  {salvos} sessoes salvas")
            total += salvos
            time.sleep(10)

        return total


# %%

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Coleta resultados da F1 via FastF1.")
    parser.add_argument("--start", type=int, default=0, help="ano inicial do intervalo")
    parser.add_argument("--stop", type=int, default=0, help="ano final do intervalo")
    parser.add_argument("--years", "-y", nargs="+", type=int, help="anos avulsos")
    parser.add_argument("--modes", "-m", nargs="+", default=["R", "S"],
                        help="sessoes a coletar (R=corrida, S=sprint)")
    args = parser.parse_args()

    if args.years:
        collect = CollectResults(args.years, args.modes)

    elif args.start and args.stop:
        collect = CollectResults(range(args.start, args.stop + 1), args.modes)

    else:
        collect = CollectResults(modes=args.modes)

    total = collect.process_years()
    print(f"\nTotal: {total} sessoes coletadas.")

# %%